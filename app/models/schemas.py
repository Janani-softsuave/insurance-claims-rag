from __future__ import annotations

from typing import Literal

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


class RetrievedChunkInfo(BaseModel):
    source: str
    score: float
    text: str
    chunk_index: int


class AskResponse(BaseModel):
    trace_id: str | None = None
    question: str
    rewritten_question: str | None = None
    answer: str
    can_answer: bool
    citations: list[Citation]
    sources: list[str]
    retrieval_only: bool = False
    retrieved_chunks: list[RetrievedChunkInfo] = Field(default_factory=list)


class ClaimSummary(BaseModel):
    claim_number: str = Field(
        description="The claim number from the adjuster notes, normalized to CLM-YYYY-NNNNN form."
    )
    date_of_loss: str = Field(description="The date the loss occurred, as stated in the adjuster notes.")
    coverage_decision: Literal["covered", "denied", "partial"] = Field(
        description="Whether the claim is covered, denied, or partially covered, based ONLY on the POLICY CONTEXT."
    )
    excess_amount: float = Field(
        description="The excess/deductible amount in rupees that applies to this claim, from the POLICY CONTEXT."
    )
    exclusion_clause_id: str | None = Field(
        default=None,
        description="The endorsement code or named exclusion from the POLICY CONTEXT that justifies a denial. "
        "Required when coverage_decision is 'denied'; null otherwise.",
    )
    summary: str = Field(description="A concise 2-4 sentence prose summary of the claim for the claims file.")
    citations: list[Citation] = Field(
        default_factory=list, description="Policy document sources supporting the coverage decision."
    )


class IngestResponse(BaseModel):
    documents_loaded: int
    chunks_indexed: int
    collection: str
    chunk_size: int
    chunk_overlap: int
