from __future__ import annotations

from app.core.config import settings
from app.core.logging import get_logger
from app.generation.generator import get_generator
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


def _retrieval_only_response(
    question: str, rewritten: str | None, reranked: list[RetrievedChunk]
) -> AskResponse:
    combined = "\n\n---\n\n".join(
        f"[{rc.chunk.source}]\n{rc.chunk.text.strip()}" for rc in reranked
    )
    return AskResponse(
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
            logger.info("RagService initialized with hybrid retrieval")
        else:
            self._retriever = Retriever()
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
        question = validate_question(question)
        rewritten: str | None = None

        # Step 1: Query transformation — HyDE takes priority over query rewriting
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
            else:
                search_query = question
            candidates = self._retriever.retrieve(search_query, top_k=top_k or settings.top_k)

        # Step 2: Cross-encoder reranking
        reranked = self.reranker.rerank(
            question, candidates, top_n=rerank_top_n or settings.rerank_top_n
        )

        # Step 3: MMR diversity reranking (applied after cross-encoder)
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

        # Step 4: Grounding gate
        if not is_grounded(reranked):
            return AskResponse(
                question=question,
                rewritten_question=rewritten,
                answer=_REFUSAL,
                can_answer=False,
                citations=[],
                sources=[],
                retrieved_chunks=_chunk_infos(reranked),
            )

        # Step 5: Grounded generation
        try:
            result: GroundedAnswer = get_generator().generate(question, reranked)
        except Exception as exc:
            logger.warning("Generation failed (%s) — falling back to retrieval only.", exc)
            return _retrieval_only_response(question, rewritten, reranked)

        if not result.can_answer:
            return AskResponse(
                question=question,
                rewritten_question=rewritten,
                answer=result.answer or _REFUSAL,
                can_answer=False,
                citations=result.citations,
                sources=[],
                retrieved_chunks=_chunk_infos(reranked),
            )

        return AskResponse(
            question=question,
            rewritten_question=rewritten,
            answer=result.answer,
            can_answer=True,
            citations=result.citations,
            sources=sorted({rc.chunk.source for rc in reranked}),
            retrieved_chunks=_chunk_infos(reranked),
        )
