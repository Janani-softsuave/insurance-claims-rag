"""RAG service — the query pipeline end to end.

Wires the pieces together in the order the Week-3 brief describes:

    validate -> embed query -> retrieve top-K -> rerank -> ground-check -> generate

This is the single entry point both the CLI and the API call, so the two
interfaces behave identically.
"""
from __future__ import annotations

from app.core.config import settings
from app.core.logging import get_logger
from app.generation.generator import get_generator
from app.guardrails.guards import is_grounded, validate_question
from app.models.schemas import AskResponse, GroundedAnswer
from app.retrieval.reranker import get_reranker
from app.retrieval.retriever import Retriever

logger = get_logger(__name__)

_REFUSAL = (
    "I don't know — I couldn't find an answer to that in the documents I have."
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
        # 1. Guardrail: validate & screen input (raises InputValidationError on bad input).
        question = validate_question(question)

        # 2. Dense retrieval (bi-encoder) then 3. rerank (cross-encoder).
        candidates = self.retriever.retrieve(question, top_k=top_k or settings.top_k)
        reranked = self.reranker.rerank(
            question, candidates, top_n=rerank_top_n or settings.rerank_top_n
        )

        # 4. Grounding guardrail — refuse instead of guessing.
        if not is_grounded(reranked):
            return AskResponse(
                question=question,
                answer=_REFUSAL,
                can_answer=False,
                citations=[],
                sources=[],
            )

        # 5. Grounded, cited generation (lazily create generator so retrieval-only
        #    flows / evaluate_chunking don't require a Gemini key).
        result: GroundedAnswer = get_generator().generate(question, reranked)

        # If the model itself decides the context is insufficient, honor that.
        if not result.can_answer:
            return AskResponse(
                question=question,
                answer=result.answer or _REFUSAL,
                can_answer=False,
                citations=result.citations,
                sources=[],
            )

        sources = sorted({rc.chunk.source for rc in reranked})
        return AskResponse(
            question=question,
            answer=result.answer,
            can_answer=True,
            citations=result.citations,
            sources=sources,
        )
