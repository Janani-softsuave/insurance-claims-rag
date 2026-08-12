"""Cross-encoder reranker — the precision stage (Week-3 bi- vs cross-encoder).

A bi-encoder embeds query and chunk separately (fast, approximate). A
cross-encoder reads the (query, chunk) pair *together* and scores relevance
directly — more accurate but too slow to run over the whole corpus. So we only
rerank the handful of candidates the dense retriever already surfaced.

Raw BGE-reranker scores are logits; we squash them through a sigmoid to a 0..1
relevance score, which the grounding guardrail then thresholds.
"""
from __future__ import annotations

import math
from functools import lru_cache

from sentence_transformers import CrossEncoder

from app.core.config import settings
from app.core.logging import get_logger
from app.models.schemas import RetrievedChunk

logger = get_logger(__name__)


def _sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))


class Reranker:
    def __init__(self, model_name: str | None = None):
        self.model_name = model_name or settings.reranker_model
        logger.info("Loading reranker model: %s", self.model_name)
        self.model = CrossEncoder(self.model_name)

    def rerank(
        self,
        query: str,
        candidates: list[RetrievedChunk],
        top_n: int | None = None,
    ) -> list[RetrievedChunk]:
        if not candidates:
            return []
        top_n = top_n or settings.rerank_top_n

        pairs = [(query, c.chunk.text) for c in candidates]
        raw_scores = self.model.predict(pairs)

        reranked = [
            RetrievedChunk(chunk=c.chunk, score=_sigmoid(float(s)))
            for c, s in zip(candidates, raw_scores)
        ]
        reranked.sort(key=lambda r: r.score, reverse=True)
        logger.info(
            "Reranked %d candidate(s); top score=%.3f",
            len(reranked),
            reranked[0].score if reranked else 0.0,
        )
        return reranked[:top_n]


@lru_cache
def get_reranker() -> Reranker:
    """Cached singleton — the cross-encoder is heavy, load it once."""
    return Reranker()
