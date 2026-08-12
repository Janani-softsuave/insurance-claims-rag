from __future__ import annotations

import chromadb
from chromadb.config import Settings as ChromaSettings

from app.core.config import settings
from app.core.logging import get_logger
from app.models.schemas import Chunk, RetrievedChunk

logger = get_logger(__name__)


class ChromaStore:
    def __init__(self, path: str | None = None, collection_name: str | None = None):
        self.path = path or settings.chroma_path
        self.collection_name = collection_name or settings.collection_name
        self.client = chromadb.PersistentClient(
            path=self.path, settings=ChromaSettings(anonymized_telemetry=False)
        )
        self.collection = self.client.get_or_create_collection(
            name=self.collection_name,
            metadata={"hnsw:space": "cosine"},
        )

    def add(self, chunks: list[Chunk], embeddings: list[list[float]]) -> None:
        if not chunks:
            return
        self.collection.upsert(
            ids=[c.id for c in chunks],
            embeddings=embeddings,
            documents=[c.text for c in chunks],
            metadatas=[
                {"source": c.source, "source_path": c.source_path, "chunk_index": c.chunk_index, **c.metadata}
                for c in chunks
            ],
        )
        logger.info("Upserted %d chunk(s) into '%s'", len(chunks), self.collection_name)

    def query(
        self,
        embedding: list[float],
        top_k: int | None = None,
        where: dict | None = None,
    ) -> list[RetrievedChunk]:
        top_k = top_k or settings.top_k
        result = self.collection.query(
            query_embeddings=[embedding],
            n_results=top_k,
            where=where,
            include=["documents", "metadatas", "distances"],
        )

        retrieved: list[RetrievedChunk] = []
        for cid, text, meta, dist in zip(
            result["ids"][0], result["documents"][0], result["metadatas"][0], result["distances"][0]
        ):
            meta = dict(meta or {})
            chunk = Chunk(
                id=cid,
                text=text,
                source=meta.get("source", "unknown"),
                source_path=meta.get("source_path", ""),
                chunk_index=int(meta.get("chunk_index", 0)),
                metadata=meta,
            )
            # Chroma returns cosine distance; convert to similarity.
            retrieved.append(RetrievedChunk(chunk=chunk, score=1.0 - float(dist)))
        return retrieved

    def count(self) -> int:
        return self.collection.count()

    def reset(self) -> None:
        self.client.delete_collection(self.collection_name)
        self.collection = self.client.get_or_create_collection(
            name=self.collection_name,
            metadata={"hnsw:space": "cosine"},
        )
        logger.info("Reset collection '%s'", self.collection_name)


def get_store() -> ChromaStore:
    return ChromaStore()
