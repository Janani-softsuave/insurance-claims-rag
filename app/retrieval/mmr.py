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
    """
    Maximal Marginal Relevance — selects chunks that are relevant to the query
    but not redundant with each other.

    MMR score = λ * sim(chunk, query) - (1 - λ) * max(sim(chunk, selected))

    λ = 1.0 → pure relevance (same as no MMR)
    λ = 0.0 → pure diversity
    λ = 0.5 → balanced (default)
    """
    top_n = top_n or settings.rerank_top_n
    lambda_ = lambda_ if lambda_ is not None else settings.mmr_lambda
    embedder = embedder or get_embedder()

    if not candidates:
        return []

    chunk_texts = [rc.chunk.text for rc in candidates]
    chunk_vectors = embedder.embed_documents(chunk_texts)

    # Relevance of each candidate to the query (already computed as score from reranker)
    # We use the stored score as relevance rather than re-embedding, since the
    # cross-encoder score is more accurate than raw cosine.
    relevance = [rc.score for rc in candidates]

    selected_indices: list[int] = []
    remaining = list(range(len(candidates)))

    while remaining and len(selected_indices) < top_n:
        if not selected_indices:
            # First pick: highest relevance
            best = max(remaining, key=lambda i: relevance[i])
        else:
            # MMR: balance relevance and redundancy
            selected_vecs = [chunk_vectors[i] for i in selected_indices]

            def mmr_score(i: int) -> float:
                rel = relevance[i]
                max_sim = max(_cosine(chunk_vectors[i], sv) for sv in selected_vecs)
                return lambda_ * rel - (1 - lambda_) * max_sim

            best = max(remaining, key=mmr_score)

        selected_indices.append(best)
        remaining.remove(best)

    result = [candidates[i] for i in selected_indices]
    logger.info("MMR selected %d chunk(s) from %d candidates (λ=%.2f)", len(result), len(candidates), lambda_)
    return result
