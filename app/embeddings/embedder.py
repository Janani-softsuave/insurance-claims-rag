from __future__ import annotations

from functools import lru_cache

from sentence_transformers import SentenceTransformer

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


class Embedder:
    def __init__(self, model_name: str | None = None, query_instruction: str | None = None):
        self.model_name = model_name or settings.embedding_model
        self.query_instruction = (
            query_instruction if query_instruction is not None else settings.query_instruction
        )
        logger.info("Loading embedding model: %s", self.model_name)
        self.model = SentenceTransformer(self.model_name)

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return self.model.encode(texts, normalize_embeddings=True, show_progress_bar=False).tolist()

    def embed_query(self, text: str) -> list[float]:
        # BGE v1.5 requires an instruction prefix on queries for better retrieval accuracy.
        return self.model.encode(
            self.query_instruction + text, normalize_embeddings=True, show_progress_bar=False
        ).tolist()


@lru_cache
def get_embedder() -> Embedder:
    return Embedder()
