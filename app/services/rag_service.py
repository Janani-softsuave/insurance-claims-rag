from __future__ import annotations

from time import perf_counter

from app.core.config import settings
from app.core.logging import get_logger
from app.core.tracing import RetrievedChunkTrace, Trace, new_trace_id, redact, utc_now_iso, write_trace
from app.generation.generator import GenerationTrace, get_generator
from app.guardrails.guards import is_grounded, validate_question
from app.models.schemas import AskResponse, GroundedAnswer, RetrievedChunk, RetrievedChunkInfo
from app.retrieval.reranker import get_reranker
from app.retrieval.retriever import Retriever

logger = get_logger(__name__)

_REFUSAL = "I don't know — I couldn't find an answer to that in the documents I have."


def _chunk_infos(chunks: list[RetrievedChunk]) -> list[RetrievedChunkInfo]:
    return [
        RetrievedChunkInfo(
            source=rc.chunk.source,
            score=round(rc.score, 4),
            text=rc.chunk.text[:300],
            chunk_index=rc.chunk.chunk_index,
        )
        for rc in chunks
    ]


def _chunk_traces(chunks: list[RetrievedChunk]) -> list[RetrievedChunkTrace]:
    return [
        RetrievedChunkTrace(
            chunk_id=rc.chunk.id,
            source=rc.chunk.source,
            chunk_index=rc.chunk.chunk_index,
            score=round(rc.score, 4),
        )
        for rc in chunks
    ]


def _retrieval_only_response(
    trace_id: str, question: str, rewritten: str | None, reranked: list[RetrievedChunk]
) -> AskResponse:
    combined = "\n\n---\n\n".join(
        f"[{rc.chunk.source}]\n{rc.chunk.text.strip()}" for rc in reranked
    )
    return AskResponse(
        trace_id=trace_id,
        question=question,
        rewritten_question=rewritten,
        answer=combined,
        can_answer=True,
        citations=[],
        sources=sorted({rc.chunk.source for rc in reranked}),
        retrieval_only=True,
        retrieved_chunks=_chunk_infos(reranked),
    )


class RagService:
    def __init__(self, use_hybrid: bool = False):
        if use_hybrid:
            from app.retrieval.hybrid_retriever import HybridRetriever
            self._retriever = HybridRetriever()
            self._retrieval_mode = "hybrid"
            logger.info("RagService initialized with hybrid retrieval")
        else:
            self._retriever = Retriever()
            self._retrieval_mode = "dense"
            logger.info("RagService initialized with dense retrieval")
        self.reranker = get_reranker()

    def ask(
        self,
        question: str,
        top_k: int | None = None,
        rerank_top_n: int | None = None,
        use_query_rewriting: bool = False,
        use_mmr: bool = False,
        mmr_lambda: float | None = None,
        use_hyde: bool = False,
    ) -> AskResponse:
        trace_id = new_trace_id()
        started = perf_counter()
        question = validate_question(question)
        question_redacted, pii_redacted = redact(question)

        retrieval_mode = "hyde" if use_hyde else self._retrieval_mode
        rewritten: str | None = None

        if use_hyde:
            from app.retrieval.hyde import hyde_embed
            from app.vectorstore.chroma_store import get_store
            query_vector = hyde_embed(question)
            candidates = get_store().query(query_vector, top_k=top_k or settings.top_k)
            logger.info("HyDE retrieval returned %d candidate(s)", len(candidates))
        else:
            if use_query_rewriting:
                from app.retrieval.query_rewriter import rewrite_query
                rewritten = rewrite_query(question)
                search_query = rewritten if rewritten != question else question
                retrieval_mode += "+rewrite"
            else:
                search_query = question
            candidates = self._retriever.retrieve(search_query, top_k=top_k or settings.top_k)

        reranked = self.reranker.rerank(
            question, candidates, top_n=rerank_top_n or settings.rerank_top_n
        )

        if use_mmr and reranked:
            from app.embeddings.embedder import get_embedder
            from app.retrieval.mmr import mmr_rerank
            query_vec = get_embedder().embed_query(question)
            reranked = mmr_rerank(
                query_vector=query_vec,
                candidates=reranked,
                top_n=rerank_top_n or settings.rerank_top_n,
                lambda_=mmr_lambda,
            )
            retrieval_mode += "+mmr"

        rewritten_redacted = redact(rewritten)[0] if rewritten else None
        chunk_traces = _chunk_traces(reranked)

        if not is_grounded(reranked):
            response = AskResponse(
                trace_id=trace_id,
                question=question,
                rewritten_question=rewritten,
                answer=_REFUSAL,
                can_answer=False,
                citations=[],
                sources=[],
                retrieved_chunks=_chunk_infos(reranked),
            )
            self._write_trace(
                trace_id=trace_id,
                question_redacted=question_redacted,
                pii_redacted=pii_redacted,
                rewritten_question=rewritten_redacted,
                retrieval_mode=retrieval_mode,
                chunk_traces=chunk_traces,
                response=response,
                generation=None,
                started=started,
                missing_fields=["model, generation_params, raw_output — no LLM call was made because retrieval did not clear the grounding threshold"],
            )
            return response

        try:
            gen_trace: GenerationTrace = get_generator().generate(question, reranked)
        except Exception as exc:
            logger.warning("Generation failed (%s) — falling back to retrieval only.", exc)
            response = _retrieval_only_response(trace_id, question, rewritten, reranked)
            self._write_trace(
                trace_id=trace_id,
                question_redacted=question_redacted,
                pii_redacted=pii_redacted,
                rewritten_question=rewritten_redacted,
                retrieval_mode=retrieval_mode,
                chunk_traces=chunk_traces,
                response=response,
                generation=None,
                started=started,
                missing_fields=[f"raw_output — generation call raised {exc.__class__.__name__}: {exc}"],
            )
            return response

        result: GroundedAnswer = gen_trace.answer
        response = AskResponse(
            trace_id=trace_id,
            question=question,
            rewritten_question=rewritten,
            answer=result.answer if result.can_answer else (result.answer or _REFUSAL),
            can_answer=result.can_answer,
            citations=result.citations if result.can_answer else [],
            sources=sorted({rc.chunk.source for rc in reranked}) if result.can_answer else [],
            retrieved_chunks=_chunk_infos(reranked),
        )

        missing_fields = [gen_trace.raw_output_note] if gen_trace.raw_output_note else []
        self._write_trace(
            trace_id=trace_id,
            question_redacted=question_redacted,
            pii_redacted=pii_redacted,
            rewritten_question=rewritten_redacted,
            retrieval_mode=retrieval_mode,
            chunk_traces=chunk_traces,
            response=response,
            generation=gen_trace,
            started=started,
            missing_fields=missing_fields,
        )
        return response

    @staticmethod
    def _write_trace(
        *,
        trace_id: str,
        question_redacted: str,
        pii_redacted: bool,
        rewritten_question: str | None,
        retrieval_mode: str,
        chunk_traces: list[RetrievedChunkTrace],
        response: AskResponse,
        generation: GenerationTrace | None,
        started: float,
        missing_fields: list[str],
    ) -> None:
        answer_redacted, answer_pii_redacted = redact(response.answer)
        write_trace(
            Trace(
                trace_id=trace_id,
                timestamp=utc_now_iso(),
                question_redacted=question_redacted,
                pii_redacted=pii_redacted or answer_pii_redacted,
                rewritten_question=rewritten_question,
                retrieval_mode=retrieval_mode,
                prompt_version=generation.prompt_version if generation else None,
                model=generation.model if generation else None,
                generation_params=generation.generation_params if generation else {},
                retrieved_chunks=chunk_traces,
                can_answer=response.can_answer,
                retrieval_only=response.retrieval_only,
                answer_redacted=answer_redacted,
                citations=[c.model_dump() for c in response.citations],
                raw_output=generation.raw_output if generation else None,
                latency_ms=int((perf_counter() - started) * 1000),
                missing_fields=missing_fields,
            )
        )
