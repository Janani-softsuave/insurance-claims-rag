from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from app.core.config import ROOT_DIR
from app.core.tracing import redact

TRACES_PATH = ROOT_DIR / "analysis" / "week11" / "traces.jsonl"


@dataclass
class Span:
    name: str
    stage: str
    latency_ms: float
    tokens: int = 0
    cost_usd: float = 0.0
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "stage": self.stage,
            "latency_ms": round(self.latency_ms, 2),
            "tokens": self.tokens,
            "cost_usd": round(self.cost_usd, 8),
            "metadata": self.metadata,
        }


@dataclass
class RequestTrace:
    trace_id: str
    timestamp: str
    user: str
    claim_number: str
    input_type: str
    prompt_version: str
    spans: list[Span] = field(default_factory=list)
    retrieved_context_ids: list[str] = field(default_factory=list)
    final_status: str | None = None
    final_payout: float | None = None
    rationale_redacted: str | None = None
    synthetic: bool = False

    @property
    def total_latency_ms(self) -> float:
        return sum(s.latency_ms for s in self.spans)

    @property
    def total_tokens(self) -> int:
        return sum(s.tokens for s in self.spans)

    @property
    def total_cost_usd(self) -> float:
        return sum(s.cost_usd for s in self.spans)

    def to_dict(self) -> dict:
        return {
            "trace_id": self.trace_id,
            "timestamp": self.timestamp,
            "user": self.user,
            "claim_number": self.claim_number,
            "input_type": self.input_type,
            "prompt_version": self.prompt_version,
            "spans": [s.to_dict() for s in self.spans],
            "retrieved_context_ids": self.retrieved_context_ids,
            "final_status": self.final_status,
            "final_payout": self.final_payout,
            "rationale_redacted": self.rationale_redacted,
            "total_latency_ms": round(self.total_latency_ms, 2),
            "total_tokens": self.total_tokens,
            "total_cost_usd": round(self.total_cost_usd, 8),
            "synthetic": self.synthetic,
        }


def new_trace_id() -> str:
    return uuid.uuid4().hex[:12]


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def redact_rationale(rationale: str | None) -> str | None:
    if not rationale:
        return rationale
    redacted, _ = redact(rationale)
    return redacted


def append_trace(trace: RequestTrace, path: Path = TRACES_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(trace.to_dict(), ensure_ascii=False) + "\n")


def read_traces(path: Path = TRACES_PATH) -> list[dict]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]
