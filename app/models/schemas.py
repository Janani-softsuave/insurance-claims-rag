from __future__ import annotations

from pydantic import BaseModel, Field


class Document(BaseModel):
    text: str
    source: str
    source_path: str
    metadata: dict = Field(default_factory=dict)


class Chunk(BaseModel):
    id: str
    text: str
    source: str
    source_path: str
    chunk_index: int
    metadata: dict = Field(default_factory=dict)


class RetrievedChunk(BaseModel):
    chunk: Chunk
    score: float


class Citation(BaseModel):
    source: str = Field(description="The document filename the fact came from.")
    snippet: str = Field(description="A short quote from that document supporting the answer.")


class GroundedAnswer(BaseModel):
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


class AskResponse(BaseModel):
    question: str
    answer: str
    can_answer: bool
    citations: list[Citation]
    sources: list[str]
    retrieval_only: bool = False


class IngestResponse(BaseModel):
    documents_loaded: int
    chunks_indexed: int
    collection: str
    chunk_size: int
    chunk_overlap: int
