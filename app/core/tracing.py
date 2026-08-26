from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from pathlib import Path

from pydantic import BaseModel, Field

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

TRACE_SCHEMA_VERSION = "1.0"

REDACTION_LIMITATIONS = (
    "Regex redaction only catches claim/policy numbers, emails, phone numbers, and "
    "names introduced by a labelling phrase such as 'my name is X' or 'claimant: X'. "
    "A bare name typed with no lead-in phrase is not reliably caught."
)

_CLAIM_NUMBER_RE = re.compile(r"\b(?:CLM|CLAIM)[-\s]?\d{4,}(?:[-/]\d+)*\b", re.IGNORECASE)
_POLICY_NUMBER_RE = re.compile(r"\b(?:POL|POLICY)[-\s]?\d{4,}(?:[-/]\d+)*\b", re.IGNORECASE)
_EMAIL_RE = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")
_PHONE_RE = re.compile(r"\b(?:\+?91[-\s]?)?[6-9]\d{9}\b")
_NAME_LABEL_RE = re.compile(
    r"(?i:\b(?:my name is|i am|i'm|claimant(?: name)?|insured(?: name)?))\s*[:\s]\s*"
    r"([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2})"
)


def redact(text: str) -> tuple[str, bool]:
    if not text:
        return text, False

    redacted = text
    hit = False
    for pattern, tag in (
        (_CLAIM_NUMBER_RE, "[REDACTED_CLAIM_NO]"),
        (_POLICY_NUMBER_RE, "[REDACTED_POLICY_NO]"),
        (_EMAIL_RE, "[REDACTED_EMAIL]"),
        (_PHONE_RE, "[REDACTED_PHONE]"),
    ):
        redacted, count = pattern.subn(tag, redacted)
        hit = hit or count > 0

    def _mask_name(match: re.Match) -> str:
        return match.group(0)[: -len(match.group(1))] + "[REDACTED_NAME]"

    redacted, count = _NAME_LABEL_RE.subn(_mask_name, redacted)
    hit = hit or count > 0

    return redacted, hit


class RetrievedChunkTrace(BaseModel):
    chunk_id: str
    source: str
    chunk_index: int
    score: float


class Trace(BaseModel):
    schema_version: str = TRACE_SCHEMA_VERSION
    trace_id: str
    timestamp: str
    question_redacted: str
    pii_redacted: bool
    rewritten_question: str | None = None
    retrieval_mode: str
    prompt_version: str | None = None
    model: str | None = None
    generation_params: dict = Field(default_factory=dict)
    retrieved_chunks: list[RetrievedChunkTrace] = Field(default_factory=list)
    can_answer: bool
    retrieval_only: bool
    answer_redacted: str
    citations: list[dict] = Field(default_factory=list)
    raw_output: str | None = None
    latency_ms: int
    missing_fields: list[str] = Field(default_factory=list)


def new_trace_id() -> str:
    return uuid.uuid4().hex[:12]


def _traces_path() -> Path:
    path = Path(settings.chroma_path).resolve().parent / "traces" / "traces.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def write_trace(trace: Trace) -> None:
    try:
        with _traces_path().open("a", encoding="utf-8") as fh:
            fh.write(trace.model_dump_json() + "\n")
    except OSError:
        logger.exception("Failed to persist trace %s — continuing without it.", trace.trace_id)


def read_traces() -> list[Trace]:
    path = _traces_path()
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as fh:
        return [Trace.model_validate_json(line) for line in fh if line.strip()]


def find_trace(trace_id: str) -> Trace | None:
    for trace in read_traces():
        if trace.trace_id == trace_id:
            return trace
    return None


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
