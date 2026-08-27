from __future__ import annotations

from dataclasses import dataclass

from app.core.logging import get_logger
from app.models.schemas import RetrievedChunk

logger = get_logger(__name__)


@dataclass
class EvalResult:
    hit_rate_at_k: float
    mrr: float
    total: int
    hits: int
    k: int

    def __str__(self) -> str:
        return (
            f"hit-rate@{self.k}={self.hit_rate_at_k:.3f}  "
            f"MRR={self.mrr:.3f}  "
            f"({self.hits}/{self.total} hits)"
        )


def hit_rate_at_k(retrieved: list[RetrievedChunk], expected_source: str, k: int) -> bool:
    sources = [rc.chunk.source for rc in retrieved[:k]]
    return expected_source in sources


def reciprocal_rank(retrieved: list[RetrievedChunk], expected_source: str) -> float:
    for i, rc in enumerate(retrieved, start=1):
        if rc.chunk.source == expected_source:
            return 1.0 / i
    return 0.0


def evaluate(
    test_queries: list[dict],
    retrieve_fn,
    k: int = 3,
) -> EvalResult:
    hits = 0
    rr_sum = 0.0

    for item in test_queries:
        question = item["question"]
        expected = item["expected_source"]
        retrieved = retrieve_fn(question)
        if hit_rate_at_k(retrieved, expected, k):
            hits += 1
        rr_sum += reciprocal_rank(retrieved, expected)

    total = len(test_queries)
    return EvalResult(
        hit_rate_at_k=hits / total if total else 0.0,
        mrr=rr_sum / total if total else 0.0,
        total=total,
        hits=hits,
        k=k,
    )
