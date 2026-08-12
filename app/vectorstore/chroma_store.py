"""Vector store — ChromaDB persistent collection (Week-3 topic).

Chroma indexes vectors with HNSW under the hood and persists to disk, so we
ingest once and query many times. We configure cosine space and pass our own
precomputed embeddings (from the BGE bi-encoder) rather than letting Chroma
embed for us.

`query` also supports Chroma's `where` metadata filter — the brief's
"metadata filtering" topic (e.g. restrict search to one source document).
"""
from __future__ import annotations

import chromadb
from chromadb.config import Settings as ChromaSettings

from app.core.config import settings
from app.core.logging import get_logger
from app.models.schemas import Chunk, RetrievedChunk

logger = get_logger(__name__)


class ChromaStore:
    """Thin wrapper around a persistent Chroma collection."""

    def __init__(self, path: str | None = None, collection_name: str | None = None):
        self.path = path or settings.chroma_path
        self.collection_name = collection_name or settings.collection_name
        self.client = chromadb.PersistentClient(
            path=self.path, settings=ChromaSettings(anonymized_telemetry=False)
        )
        self.collection = self.client.get_or_create_collection(
            name=self.collection_name,
            metadata={"hnsw:space": "cosine"},  # cosine distance for normalized vectors
        )

    # ----- write path ----------------------------------------------------- #
    def add(self, chunks: list[Chunk], embeddings: list[list[float]]) -> None:
        """Upsert chunks + their vectors. `id` dedupes re-ingested content."""
        if not chunks:
            return
        self.collection.upsert(
            ids=[c.id for c in chunks],
            embeddings=embeddings,
            documents=[c.text for c in chunks],
            metadatas=[
                {
                    "source": c.source,
                    "source_path": c.source_path,
                    "chunk_index": c.chunk_index,
                    **{k: v for k, v in c.metadata.items()},
                }
                for c in chunks
            ],
        )
        logger.info("Upserted %d chunk(s) into '%s'", len(chunks), self.collection_name)

    # ----- read path ------------------------------------------------------ #
    def query(
        self,
        embedding: list[float],
        top_k: int | None = None,
        where: dict | None = None,
    ) -> list[RetrievedChunk]:
        """Return the top-K most similar chunks (optionally metadata-filtered)."""
        top_k = top_k or settings.top_k
        result = self.collection.query(
            query_embeddings=[embedding],
            n_results=top_k,
            where=where,
            include=["documents", "metadatas", "distances"],
        )

        ids = result["ids"][0]
        docs = result["documents"][0]
        metas = result["metadatas"][0]
        distances = result["distances"][0]

        retrieved: list[RetrievedChunk] = []
        for cid, text, meta, dist in zip(ids, docs, metas, distances):
            meta = dict(meta or {})
            chunk = Chunk(
                id=cid,
                text=text,
                source=meta.get("source", "unknown"),
                source_path=meta.get("source_path", ""),
                chunk_index=int(meta.get("chunk_index", 0)),
                metadata=meta,
            )
            # cosine distance -> similarity
            retrieved.append(RetrievedChunk(chunk=chunk, score=1.0 - float(dist)))
        return retrieved

    # ----- housekeeping --------------------------------------------------- #
    def count(self) -> int:
        return self.collection.count()

    def reset(self) -> None:
        """Drop and recreate the collection (used by `ingest --reset`)."""
        self.client.delete_collection(self.collection_name)
        self.collection = self.client.get_or_create_collection(
            name=self.collection_name,
            metadata={"hnsw:space": "cosine"},
        )
        logger.info("Reset collection '%s'", self.collection_name)


def get_store() -> ChromaStore:
    """Factory (kept as a function so callers can override path/collection)."""
    return ChromaStore()
