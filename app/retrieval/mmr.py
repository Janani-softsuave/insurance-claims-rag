from __future__ import annotations

from app.core.config import settings
from app.core.logging import get_logger
from app.embeddings.embedder import Embedder, get_embedder
from app.models.schemas import RetrievedChunk

logger = get_logger(__name__)


def _cosine(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


def mmr_rerank(
    query_vector: list[float],
    candidates: list[RetrievedChunk],
    top_n: int | None = None,
    lambda_: float | None = None,
    embedder: Embedder | None = None,
) -> list[RetrievedChunk]:
    top_n = top_n or settings.rerank_top_n
    lambda_ = settings.mmr_lambda if lambda_ is None else lambda_
    embedder = embedder or get_embedder()

    if not candidates:
        return []

    chunk_vectors = embedder.embed_documents([rc.chunk.text for rc in candidates])
    relevance = [rc.score for rc in candidates]

    selected_indices: list[int] = []
    remaining = list(range(len(candidates)))

    while remaining and len(selected_indices) < top_n:
        if not selected_indices:
            best = max(remaining, key=lambda i: relevance[i])
        else:
            selected_vecs = [chunk_vectors[i] for i in selected_indices]

            def mmr_score(i: int) -> float:
                return lambda_ * relevance[i] - (1 - lambda_) * max(
                    _cosine(chunk_vectors[i], sv) for sv in selected_vecs
                )

            best = max(remaining, key=mmr_score)

        selected_indices.append(best)
        remaining.remove(best)

    result = [candidates[i] for i in selected_indices]
    logger.info("MMR selected %d chunk(s) from %d candidates (λ=%.2f)", len(result), len(candidates), lambda_)
    return result
