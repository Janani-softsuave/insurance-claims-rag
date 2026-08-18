from __future__ import annotations

from app.core.config import settings
from app.core.logging import get_logger
from app.models.schemas import Chunk, RetrievedChunk
from app.retrieval.bm25_retriever import BM25Retriever
from app.retrieval.retriever import Retriever
from app.vectorstore.chroma_store import ChromaStore, get_store

logger = get_logger(__name__)


def _rrf_score(rank: int, k: int = 60) -> float:
    return 1.0 / (k + rank + 1)


def _load_all_chunks(store: ChromaStore) -> list[Chunk]:
    result = store.collection.get(include=["documents", "metadatas"])
    chunks: list[Chunk] = []
    for cid, text, meta in zip(result["ids"], result["documents"], result["metadatas"]):
        meta = dict(meta or {})
        chunks.append(Chunk(
            id=cid,
            text=text,
            source=meta.get("source", "unknown"),
            source_path=meta.get("source_path", ""),
            chunk_index=int(meta.get("chunk_index", 0)),
            metadata=meta,
        ))
    return chunks


class HybridRetriever:
    def __init__(self, store: ChromaStore | None = None):
        self.store = store or get_store()
        self.dense = Retriever(store=self.store)
        chunks = _load_all_chunks(self.store)
        self.bm25 = BM25Retriever(chunks)

    def retrieve(self, query: str, top_k: int | None = None) -> list[RetrievedChunk]:
        top_k = top_k or settings.top_k
        k = settings.rrf_k

        dense_results = self.dense.retrieve(query, top_k=top_k)
        bm25_results = self.bm25.retrieve(query, top_k=settings.bm25_top_k)

        # Reciprocal Rank Fusion — merge by chunk id
        rrf_scores: dict[str, float] = {}
        chunk_map: dict[str, Chunk] = {}

        for rank, rc in enumerate(dense_results):
            rrf_scores[rc.chunk.id] = rrf_scores.get(rc.chunk.id, 0) + _rrf_score(rank, k)
            chunk_map[rc.chunk.id] = rc.chunk

        for rank, rc in enumerate(bm25_results):
            rrf_scores[rc.chunk.id] = rrf_scores.get(rc.chunk.id, 0) + _rrf_score(rank, k)
            chunk_map[rc.chunk.id] = rc.chunk

        merged = sorted(rrf_scores.items(), key=lambda x: x[1], reverse=True)[:top_k]
        results = [RetrievedChunk(chunk=chunk_map[cid], score=score) for cid, score in merged]

        logger.info("Hybrid retrieval (RRF) returned %d candidate(s)", len(results))
        return results
