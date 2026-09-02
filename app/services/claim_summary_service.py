from __future__ import annotations

from app.core.config import settings
from app.core.logging import get_logger
from app.generation.claim_summarizer import get_claim_summarizer
from app.models.schemas import ClaimSummary, RetrievedChunk
from app.retrieval.reranker import get_reranker
from app.retrieval.retriever import Retriever

logger = get_logger(__name__)


class ClaimSummaryService:
    def __init__(self) -> None:
        self._retriever = Retriever()
        self._reranker = get_reranker()

    def summarize(
        self,
        adjuster_notes: str,
        top_k: int | None = None,
        rerank_top_n: int | None = None,
    ) -> tuple[ClaimSummary, list[RetrievedChunk]]:
        candidates = self._retriever.retrieve(adjuster_notes, top_k=top_k or settings.top_k)
        reranked = self._reranker.rerank(adjuster_notes, candidates, top_n=rerank_top_n or settings.rerank_top_n)
        summary = get_claim_summarizer().summarize(adjuster_notes, reranked)
        return summary, reranked
