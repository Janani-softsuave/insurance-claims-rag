from __future__ import annotations

from app.core.config import settings
from app.core.logging import get_logger
from app.embeddings.embedder import get_embedder
from app.models.schemas import RetrievedChunk
from app.vectorstore.chroma_store import ChromaStore, get_store

logger = get_logger(__name__)


class Retriever:
    def __init__(self, store: ChromaStore | None = None):
        self.store = store or get_store()
        self.embedder = get_embedder()

    def retrieve(
        self,
        query: str,
        top_k: int | None = None,
        where: dict | None = None,
    ) -> list[RetrievedChunk]:
        top_k = top_k or settings.top_k
        query_vector = self.embedder.embed_query(query)
        results = self.store.query(query_vector, top_k=top_k, where=where)
        logger.info("Dense retrieval returned %d candidate(s)", len(results))
        return results
