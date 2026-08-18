from __future__ import annotations

import re

from rank_bm25 import BM25Okapi

from app.core.config import settings
from app.core.logging import get_logger
from app.models.schemas import Chunk, RetrievedChunk

logger = get_logger(__name__)


def _tokenize(text: str) -> list[str]:
    return re.findall(r"\w+", text.lower())


class BM25Retriever:
    def __init__(self, chunks: list[Chunk]):
        self.chunks = chunks
        tokenized = [_tokenize(c.text) for c in chunks]
        self.index = BM25Okapi(tokenized)
        logger.info("BM25 index built over %d chunks", len(chunks))

    def retrieve(self, query: str, top_k: int | None = None) -> list[RetrievedChunk]:
        top_k = top_k or settings.bm25_top_k
        tokens = _tokenize(query)
        scores = self.index.get_scores(tokens)
        top_indices = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:top_k]
        results = [
            RetrievedChunk(chunk=self.chunks[i], score=float(scores[i]))
            for i in top_indices
            if scores[i] > 0
        ]
        logger.info("BM25 retrieval returned %d candidate(s)", len(results))
        return results
