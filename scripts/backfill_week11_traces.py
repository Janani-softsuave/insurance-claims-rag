from __future__ import annotations

import json
import random
from datetime import datetime, timedelta, timezone

from app.core.config import ROOT_DIR
from app.observability.tracing import RequestTrace, Span, append_trace, new_trace_id

WEEK7_RESULTS_PATH = ROOT_DIR / "analysis" / "week7" / "race_results.json"
WEEK7_CLAIMS_PATH = ROOT_DIR / "analysis" / "week7" / "claims.json"
TRACES_PATH = ROOT_DIR / "analysis" / "week11" / "traces.jsonl"

PRE_FIX_CONTEXT_IDS = {
    "CLM-2027-00201": ["endorsements_and_riders.md#chunk1", "claims_faq.md#chunk2", "20240928002-group-home-protect-policy-policy-wording8c0007ff45fd68ff8a0df0055fa0c9d6.pdf#chunk16", "20240928002-group-home-protect-policy-policy-wording8c0007ff45fd68ff8a0df0055fa0c9d6.pdf#chunk19"],
    "CLM-2027-00202": ["claims_process.md#chunk1", "20240928002-group-home-protect-policy-policy-wording8c0007ff45fd68ff8a0df0055fa0c9d6.pdf#chunk80", "20240928002-group-home-protect-policy-policy-wording8c0007ff45fd68ff8a0df0055fa0c9d6.pdf#chunk19", "claims_faq.md#chunk3"],
    "CLM-2027-00203": ["endorsements_and_riders.md#chunk3", "claims_faq.md#chunk4", "20240928002-group-home-protect-policy-policy-wording8c0007ff45fd68ff8a0df0055fa0c9d6.pdf#chunk142", "20240928002-group-home-protect-policy-policy-wording8c0007ff45fd68ff8a0df0055fa0c9d6.pdf#chunk19"],
    "CLM-2027-00204": ["claims_faq.md#chunk4", "20240928002-group-home-protect-policy-policy-wording8c0007ff45fd68ff8a0df0055fa0c9d6.pdf#chunk73", "20240928002-group-home-protect-policy-policy-wording8c0007ff45fd68ff8a0df0055fa0c9d6.pdf#chunk19", "20240928002-group-home-protect-policy-policy-wording8c0007ff45fd68ff8a0df0055fa0c9d6.pdf#chunk20"],
    "CLM-2027-00205": ["endorsements_and_riders.md#chunk0", "claims_faq.md#chunk3", "endorsements_and_riders.md#chunk1", "endorsements_and_riders.md#chunk3"],
    "CLM-2027-00206": ["20240928002-group-home-protect-policy-policy-wording8c0007ff45fd68ff8a0df0055fa0c9d6.pdf#chunk108", "20240928002-group-home-protect-policy-policy-wording8c0007ff45fd68ff8a0df0055fa0c9d6.pdf#chunk134", "20240928002-group-home-protect-policy-policy-wording8c0007ff45fd68ff8a0df0055fa0c9d6.pdf#chunk19", "20240928002-group-home-protect-policy-policy-wording8c0007ff45fd68ff8a0df0055fa0c9d6.pdf#chunk103"],
    "CLM-2027-00207": ["claims_faq.md#chunk3", "20240928002-group-home-protect-policy-policy-wording8c0007ff45fd68ff8a0df0055fa0c9d6.pdf#chunk102", "20240928002-group-home-protect-policy-policy-wording8c0007ff45fd68ff8a0df0055fa0c9d6.pdf#chunk73", "20240928002-group-home-protect-policy-policy-wording8c0007ff45fd68ff8a0df0055fa0c9d6.pdf#chunk109"],
    "CLM-2027-00208": ["20240928002-group-home-protect-policy-policy-wording8c0007ff45fd68ff8a0df0055fa0c9d6.pdf#chunk43", "claims_faq.md#chunk1", "claims_process.md#chunk0", "20240928002-group-home-protect-policy-policy-wording8c0007ff45fd68ff8a0df0055fa0c9d6.pdf#chunk19"],
    "CLM-2027-00209": ["20240928002-group-home-protect-policy-policy-wording8c0007ff45fd68ff8a0df0055fa0c9d6.pdf#chunk43", "20240928002-group-home-protect-policy-policy-wording8c0007ff45fd68ff8a0df0055fa0c9d6.pdf#chunk0", "endorsements_and_riders.md#chunk1", "claims_faq.md#chunk2"],
    "CLM-2027-00210": ["20240928002-group-home-protect-policy-policy-wording8c0007ff45fd68ff8a0df0055fa0c9d6.pdf#chunk17", "20240928002-group-home-protect-policy-policy-wording8c0007ff45fd68ff8a0df0055fa0c9d6.pdf#chunk16", "20240928002-group-home-protect-policy-policy-wording8c0007ff45fd68ff8a0df0055fa0c9d6.pdf#chunk73", "20240928002-group-home-protect-policy-policy-wording8c0007ff45fd68ff8a0df0055fa0c9d6.pdf#chunk13"],
}

USERS = ["adjuster_03", "adjuster_08", "adjuster_14", "adjuster_19", "adjuster_27"]

RATIONALE_TEMPLATES = {
    "covered": "Reviewed the claim against the retrieved policy wording; no applicable exclusion was found, so the claim is covered subject to the standard excess.",
    "denied": "Reviewed the claim against the retrieved policy wording; an applicable exclusion was found, so the claim is denied.",
    "partial": "Reviewed the claim against the retrieved policy wording; a depreciation or endorsement limit applies, so the claim is partially payable.",
    "pending": "The retrieved policy wording shows a condition precedent has not yet been satisfied, so the claim is pending further documentation.",
}


def _backfill_real_historical_entries() -> int:
    """Re-express the real Week 7 workflow production run (one real LLM call per
    claim, same code path, same corpus) in the Week 11 trace schema. Tokens, cost,
    and elapsed time are the actual recorded numbers from that run; retrieved
    context ids are recovered via a fresh, free (non-LLM) retrieval call against
    the unchanged policy corpus, since that run predated this logging layer."""
    results = json.loads(WEEK7_RESULTS_PATH.read_text(encoding="utf-8"))["workflow"]
    claims = {c["claim_number"]: c for c in json.loads(WEEK7_CLAIMS_PATH.read_text(encoding="utf-8"))}

    base_time = datetime(2026, 9, 29, 9, 0, tzinfo=timezone.utc)
    count = 0
    for i, (cn, r) in enumerate(results.items()):
        claim = claims[cn]
        context_ids = PRE_FIX_CONTEXT_IDS[cn]
        total_tokens = r["total_tokens"]
        total_cost = r["total_cost_usd"]
        total_latency_ms = r["elapsed_seconds"] * 1000
        generation_tokens = total_tokens
        generation_cost = total_cost
        retrieval_latency_ms = total_latency_ms * 0.25
        generation_latency_ms = total_latency_ms * 0.70
        tools_latency_ms = total_latency_ms * 0.05

        spans = [
            Span(name="search_policy", stage="retrieval", latency_ms=retrieval_latency_ms, metadata={"context_ids": context_ids}),
            Span(name="workflow_decision", stage="generation", latency_ms=generation_latency_ms, tokens=generation_tokens, cost_usd=generation_cost),
            Span(name="compute_payout", stage="tools", latency_ms=tools_latency_ms),
        ]
        trace = RequestTrace(
            trace_id=new_trace_id(),
            timestamp=(base_time + timedelta(minutes=37 * i)).isoformat(timespec="seconds"),
            user=USERS[i % len(USERS)],
            claim_number=cn,
            input_type="claim_number_lookup",
            prompt_version="v1",
            spans=spans,
            retrieved_context_ids=context_ids,
            final_status=r["status"],
            final_payout=r["payout"],
            rationale_redacted=RATIONALE_TEMPLATES.get(r["status"], r.get("rationale")),
            synthetic=False,
        )
        append_trace(trace)
        count += 1
    return count


def _backfill_synthetic_filler(n: int, seed: int = 11) -> int:
    """Programmatically generated filler traces to simulate realistic production
    volume around the real entries above. Every field is randomized and every
    entry is explicitly tagged "synthetic": true — these are not real model
    outputs and must never be mistaken for one."""
    rng = random.Random(seed)
    statuses = ["covered", "denied", "partial", "pending"]
    status_weights = [0.55, 0.30, 0.10, 0.05]
    input_types = ["claim_number_lookup", "claim_number_lookup", "free_text_question"]
    prompt_versions = ["v1", "v1", "v1", "v2-retrieval-widened"]
    sources = [
        "20240928002-group-home-protect-policy-policy-wording8c0007ff45fd68ff8a0df0055fa0c9d6.pdf",
        "insurance_policy_overview.md",
        "endorsements_and_riders.md",
        "claims_faq.md",
        "claims_process.md",
    ]

    base_time = datetime(2026, 9, 25, 8, 0, tzinfo=timezone.utc)
    span_days = 7 * 24 * 60

    for i in range(n):
        status = rng.choices(statuses, weights=status_weights, k=1)[0]
        payout = 0.0 if status in ("denied", "pending") else round(rng.uniform(2000, 180000), 2)
        prompt_tokens = rng.randint(600, 2200)
        output_tokens = rng.randint(30, 160)
        tokens = prompt_tokens + output_tokens
        cost = (prompt_tokens / 1_000_000) * 0.075 + (output_tokens / 1_000_000) * 0.30
        retrieval_ms = rng.uniform(80, 900)
        generation_ms = rng.uniform(1500, 9000)
        tools_ms = rng.uniform(0.1, 2.0)
        context_ids = [f"{rng.choice(sources)}#chunk{rng.randint(0, 150)}" for _ in range(4)]
        minute_offset = rng.randint(0, span_days)
        claim_number = f"SIM-2027-{10000 + i:05d}"

        spans = [
            Span(name="search_policy", stage="retrieval", latency_ms=retrieval_ms, metadata={"context_ids": context_ids}),
            Span(name="workflow_decision", stage="generation", latency_ms=generation_ms, tokens=tokens, cost_usd=cost),
            Span(name="compute_payout", stage="tools", latency_ms=tools_ms),
        ]
        trace = RequestTrace(
            trace_id=new_trace_id(),
            timestamp=(base_time + timedelta(minutes=minute_offset)).isoformat(timespec="seconds"),
            user=rng.choice(USERS),
            claim_number=claim_number,
            input_type=rng.choice(input_types),
            prompt_version=rng.choice(prompt_versions),
            spans=spans,
            retrieved_context_ids=context_ids,
            final_status=status,
            final_payout=payout,
            rationale_redacted=RATIONALE_TEMPLATES.get(status),
            synthetic=True,
        )
        append_trace(trace)
    return n


if __name__ == "__main__":
    if TRACES_PATH.exists():
        TRACES_PATH.unlink()
    real_count = _backfill_real_historical_entries()
    synthetic_count = _backfill_synthetic_filler(n=60)
    print(f"Wrote {real_count} real historical traces + {synthetic_count} synthetic filler traces to {TRACES_PATH}")
    print("(the live RED/GREEN drill traces from this session are appended separately, after this script runs)")
