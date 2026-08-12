"""Embeddings — the bi-encoder that turns text into vectors (Week-3 topic).

We use a local sentence-transformers BGE model (from the MTEB/BGE/E5 family the
brief names). Vectors are L2-normalized so cosine similarity == dot product,
which is what the vector store's HNSW index compares.

A bi-encoder embeds the query and each document *independently*; retrieval is
then a fast nearest-neighbour lookup. (The cross-encoder in reranker.py does the
opposite — it reads query+chunk together — which is slower but more accurate,
hence we only rerank the top-K.)
"""
from __future__ import annotations

from functools import lru_cache

from sentence_transformers import SentenceTransformer

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


class Embedder:
    """Wraps a sentence-transformers bi-encoder."""

    def __init__(self, model_name: str | None = None, query_instruction: str | None = None):
        self.model_name = model_name or settings.embedding_model
        self.query_instruction = (
            query_instruction if query_instruction is not None else settings.query_instruction
        )
        logger.info("Loading embedding model: %s", self.model_name)
        self.model = SentenceTransformer(self.model_name)

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Embed passages (no instruction prefix)."""
        vectors = self.model.encode(
            texts, normalize_embeddings=True, show_progress_bar=False
        )
        return vectors.tolist()

    def embed_query(self, text: str) -> list[float]:
        """Embed a search query (BGE v1.5 wants an instruction prefix)."""
        vector = self.model.encode(
            self.query_instruction + text,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        return vector.tolist()


@lru_cache
def get_embedder() -> Embedder:
    """Cached singleton — the model is heavy, load it once per process."""
    return Embedder()
