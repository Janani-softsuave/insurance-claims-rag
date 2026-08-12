"""Pydantic schemas — the typed contracts that flow through the pipelines.

Using Pydantic for the LLM's output (GroundedAnswer) is the Week-2 "structured
output your program can trust" idea: the model is *forced* to return this shape,
and instructor validates + retries until it does.
"""
from __future__ import annotations

from pydantic import BaseModel, Field


# --------------------------------------------------------------------------- #
# Ingestion-side models
# --------------------------------------------------------------------------- #
class Document(BaseModel):
    """A raw source document loaded from disk (before chunking)."""

    text: str
    source: str        # human-friendly name, e.g. "thai_green_curry.md"
    source_path: str   # absolute path on disk
    metadata: dict = Field(default_factory=dict)


class Chunk(BaseModel):
    """A single searchable piece of a document."""

    id: str
    text: str
    source: str
    source_path: str
    chunk_index: int
    metadata: dict = Field(default_factory=dict)


# --------------------------------------------------------------------------- #
# Retrieval-side models
# --------------------------------------------------------------------------- #
class RetrievedChunk(BaseModel):
    """A chunk returned by search, with its relevance score."""

    chunk: Chunk
    score: float  # cosine similarity (dense) or normalized rerank score


# --------------------------------------------------------------------------- #
# Generation-side models  (what the LLM must return)
# --------------------------------------------------------------------------- #
class Citation(BaseModel):
    """A pointer back to the source that supports the answer."""

    source: str = Field(description="The document filename the fact came from.")
    snippet: str = Field(description="A short quote from that document supporting the answer.")


class GroundedAnswer(BaseModel):
    """The grounded, cited answer the LLM is forced to produce."""

    can_answer: bool = Field(
        description="True only if the answer is fully supported by the provided context. "
        "If the context does not contain the answer, set this to False."
    )
    answer: str = Field(
        description="The answer, written ONLY from the provided context. "
        "If can_answer is False, say you don't know."
    )
    citations: list[Citation] = Field(
        default_factory=list,
        description="Sources supporting the answer. Empty when can_answer is False.",
    )


# --------------------------------------------------------------------------- #
# API request / response models
# --------------------------------------------------------------------------- #
class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=1000)
    top_k: int | None = None
    rerank_top_n: int | None = None


class AskResponse(BaseModel):
    question: str
    answer: str
    can_answer: bool
    citations: list[Citation]
    sources: list[str] = Field(description="Documents the retrieved context came from.")


class IngestResponse(BaseModel):
    documents_loaded: int
    chunks_indexed: int
    collection: str
    chunk_size: int
    chunk_overlap: int


class UploadResponse(BaseModel):
    filename: str
    saved_path: str
    chunks_indexed: int
    collection: str
    message: str
