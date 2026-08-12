from __future__ import annotations

import hashlib

from app.core.config import settings
from app.core.logging import get_logger
from app.models.schemas import Chunk, Document

logger = get_logger(__name__)

_SEPARATORS = ["\n\n", "\n", ". ", " ", ""]


def _split_recursive(text: str, chunk_size: int, separators: list[str]) -> list[str]:
    if len(text) <= chunk_size:
        return [text]

    separator = separators[0]
    remaining = separators[1:] or [""]

    if separator == "":
        return [text[i: i + chunk_size] for i in range(0, len(text), chunk_size)]

    pieces = text.split(separator)
    chunks: list[str] = []
    current = ""
    for piece in pieces:
        candidate = piece if not current else current + separator + piece
        if len(candidate) <= chunk_size:
            current = candidate
            continue
        if current:
            chunks.append(current)
        if len(piece) > chunk_size:
            chunks.extend(_split_recursive(piece, chunk_size, remaining))
            current = ""
        else:
            current = piece
    if current:
        chunks.append(current)
    return chunks


def _apply_overlap(chunks: list[str], overlap: int) -> list[str]:
    if overlap <= 0 or len(chunks) <= 1:
        return chunks
    result = [chunks[0]]
    for prev, curr in zip(chunks, chunks[1:]):
        result.append((prev[-overlap:] + " " + curr).strip())
    return result


def _chunk_id(source: str, index: int, text: str) -> str:
    digest = hashlib.sha1(f"{source}:{index}:{text}".encode()).hexdigest()[:12]
    return f"{source}::{index}::{digest}"


def chunk_document(
    document: Document,
    chunk_size: int | None = None,
    chunk_overlap: int | None = None,
) -> list[Chunk]:
    chunk_size = chunk_size or settings.chunk_size
    chunk_overlap = chunk_overlap if chunk_overlap is not None else settings.chunk_overlap

    raw = _split_recursive(document.text, chunk_size, _SEPARATORS)
    raw = [c.strip() for c in raw if c.strip()]
    raw = _apply_overlap(raw, chunk_overlap)

    return [
        Chunk(
            id=_chunk_id(document.source, i, text),
            text=text,
            source=document.source,
            source_path=document.source_path,
            chunk_index=i,
            metadata={**document.metadata, "chunk_size": chunk_size, "chunk_overlap": chunk_overlap},
        )
        for i, text in enumerate(raw)
    ]


def chunk_documents(
    documents: list[Document],
    chunk_size: int | None = None,
    chunk_overlap: int | None = None,
) -> list[Chunk]:
    all_chunks: list[Chunk] = []
    for doc in documents:
        all_chunks.extend(chunk_document(doc, chunk_size, chunk_overlap))
    logger.info(
        "Chunked %d document(s) into %d chunk(s) [size=%s, overlap=%s]",
        len(documents),
        len(all_chunks),
        chunk_size or settings.chunk_size,
        chunk_overlap if chunk_overlap is not None else settings.chunk_overlap,
    )
    return all_chunks
