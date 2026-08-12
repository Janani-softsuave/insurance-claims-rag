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
        # Raw cross-encoder scores are logits; sigmoid maps them to 0..1.
        reranked = [
            RetrievedChunk(chunk=c.chunk, score=_sigmoid(float(s)))
            for c, s in zip(candidates, self.model.predict(pairs))
        ]
        reranked.sort(key=lambda r: r.score, reverse=True)
        logger.info("Reranked %d candidate(s); top score=%.3f", len(reranked), reranked[0].score)
        return reranked[:top_n]


@lru_cache
def get_reranker() -> Reranker:
    return Reranker()
