from __future__ import annotations

from time import perf_counter
from typing import Literal

import instructor
from google import genai
from pydantic import BaseModel, Field

from app.agent.tools import compute_payout, get_claim, search_policy
from app.core.config import settings
from app.core.logging import get_logger
from app.observability.tracing import (
    RequestTrace,
    Span,
    append_trace,
    new_trace_id,
    redact_rationale,
    utc_now_iso,
)

logger = get_logger(__name__)

WORKFLOW_PROMPT_VERSION = "v2-retrieval-widened"

WORKFLOW_SYSTEM_PROMPT = """You are a claims triage assistant for ABC Insurance.

Given a claim record and retrieved policy text, decide the claim's status and
the effective excess to apply.

Rules:
1. claim_status: covered / denied / partial / pending, based ONLY on the
   adjuster notes and the retrieved policy text.
2. effective_excess_amount: the claim's excess_amount, UNLESS the policy text
   shows the deductible is waived for this specific claim (e.g. a glass-only
   claim with glass breakage cover) — then use 0.
3. Never invent a policy rule not present in the retrieved text."""


class WorkflowDecision(BaseModel):
    claim_status: Literal["covered", "denied", "partial", "pending"]
    effective_excess_amount: float
    rationale: str = Field(description="One or two sentences explaining the decision.")


def _build_user_prompt(claim: dict, chunks: list[dict]) -> str:
    context = "\n\n---\n\n".join(f"[{c['source']}]\n{c['text']}" for c in chunks)
    return (
        f"CLAIM RECORD:\n{claim}\n\n"
        f"POLICY TEXT:\n{context}\n\n"
        "Decide claim_status and effective_excess_amount now."
    )


class ClaimsWorkflow:
    def __init__(self, api_key: str | None = None, model: str | None = None):
        api_key = api_key or settings.gemini_api_key
        self.model = model or settings.gemini_model
        self.client = instructor.from_genai(genai.Client(api_key=api_key))

    def run(self, claim_number: str, user: str = "unknown", input_type: str = "claim_number_lookup") -> dict:
        started = perf_counter()
        spans: list[Span] = []

        # Step 1 — fixed: fetch the claim record.
        claim = get_claim(claim_number)

        # Step 2 — fixed, unconditional: always search policy text.
        retrieval_started = perf_counter()
        chunks = search_policy(claim["adjuster_notes"])
        retrieval_latency_ms = (perf_counter() - retrieval_started) * 1000
        context_ids = [f"{c['source']}#chunk{c['chunk_index']}" for c in chunks]
        spans.append(Span(name="search_policy", stage="retrieval", latency_ms=retrieval_latency_ms, metadata={"context_ids": context_ids}))

        # Step 3 — one fixed LLM call, no branching, no tool-calling loop.
        generation_started = perf_counter()
        decision, completion = self.client.chat.completions.create_with_completion(
            model=self.model,
            response_model=WorkflowDecision,
            max_retries=settings.max_retries,
            messages=[
                {"role": "system", "content": WORKFLOW_SYSTEM_PROMPT},
                {"role": "user", "content": _build_user_prompt(claim, chunks)},
            ],
        )
        generation_latency_ms = (perf_counter() - generation_started) * 1000
        usage = getattr(completion, "usage_metadata", None)
        prompt_tokens = getattr(usage, "prompt_token_count", 0) or 0
        output_tokens = getattr(usage, "candidates_token_count", 0) or 0
        tokens = prompt_tokens + output_tokens
        cost = (
            (prompt_tokens / 1_000_000) * settings.price_input_per_million
            + (output_tokens / 1_000_000) * settings.price_output_per_million
        )
        spans.append(Span(name="workflow_decision", stage="generation", latency_ms=generation_latency_ms, tokens=tokens, cost_usd=cost))

        # Step 4 — fixed: compute the payout.
        tools_started = perf_counter()
        payout_result = compute_payout(decision.claim_status, claim["claimed_amount"], decision.effective_excess_amount)
        tools_latency_ms = (perf_counter() - tools_started) * 1000
        spans.append(Span(name="compute_payout", stage="tools", latency_ms=tools_latency_ms))

        elapsed = perf_counter() - started

        try:
            trace = RequestTrace(
                trace_id=new_trace_id(),
                timestamp=utc_now_iso(),
                user=user,
                claim_number=claim_number,
                input_type=input_type,
                prompt_version=WORKFLOW_PROMPT_VERSION,
                spans=spans,
                retrieved_context_ids=context_ids,
                final_status=decision.claim_status,
                final_payout=payout_result.get("payout"),
                rationale_redacted=redact_rationale(decision.rationale),
            )
            append_trace(trace)
        except Exception:
            logger.exception("Failed to append request trace for %s — continuing without it.", claim_number)

        return {
            "claim_number": claim_number,
            "status": decision.claim_status,
            "payout": payout_result.get("payout"),
            "rationale": decision.rationale,
            "total_tokens": tokens,
            "total_cost_usd": cost,
            "elapsed_seconds": elapsed,
            "tool_calls": ["get_claim", "search_policy", "compute_payout"],
        }
