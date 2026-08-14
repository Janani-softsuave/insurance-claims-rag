from __future__ import annotations

from app.core.config import settings
from app.core.logging import get_logger
from app.generation.generator import get_generator
from app.guardrails.guards import is_grounded, validate_question
from app.models.schemas import AskResponse, GroundedAnswer
from app.retrieval.reranker import get_reranker
from app.retrieval.retriever import Retriever

logger = get_logger(__name__)

_REFUSAL = "I don't know — I couldn't find an answer to that in the documents I have."


def _retrieval_only_response(question: str, reranked) -> AskResponse:
    sources = sorted({rc.chunk.source for rc in reranked})
    combined = "\n\n---\n\n".join(
        f"[{rc.chunk.source}]\n{rc.chunk.text.strip()}" for rc in reranked
    )
    return AskResponse(
        question=question,
        answer=combined,
        can_answer=True,
        citations=[],
        sources=sources,
        retrieval_only=True,
    )


class RagService:
    def __init__(self):
        self.retriever = Retriever()
        self.reranker = get_reranker()

    def ask(
        self,
        question: str,
        top_k: int | None = None,
        rerank_top_n: int | None = None,
    ) -> AskResponse:
        question = validate_question(question)

        candidates = self.retriever.retrieve(question, top_k=top_k or settings.top_k)
        reranked = self.reranker.rerank(question, candidates, top_n=rerank_top_n or settings.rerank_top_n)

        if not is_grounded(reranked):
            return AskResponse(question=question, answer=_REFUSAL, can_answer=False, citations=[], sources=[])

        try:
            result: GroundedAnswer = get_generator().generate(question, reranked)
        except Exception as exc:
            logger.warning("Generation failed (%s) — falling back to retrieval only.", exc)
            return _retrieval_only_response(question, reranked)

        if not result.can_answer:
            return AskResponse(
                question=question,
                answer=result.answer or _REFUSAL,
                can_answer=False,
                citations=result.citations,
                sources=[],
            )

        return AskResponse(
            question=question,
            answer=result.answer,
            can_answer=True,
            citations=result.citations,
            sources=sorted({rc.chunk.source for rc in reranked}),
        )
