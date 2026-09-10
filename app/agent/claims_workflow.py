from __future__ import annotations

from time import perf_counter
from typing import Literal

import instructor
from google import genai
from pydantic import BaseModel, Field

from app.agent.tools import compute_payout, get_claim, search_policy
from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

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

    def run(self, claim_number: str) -> dict:
        started = perf_counter()

        # Step 1 — fixed: fetch the claim record.
        claim = get_claim(claim_number)

        # Step 2 — fixed, unconditional: always search policy text.
        chunks = search_policy(claim["adjuster_notes"])

        # Step 3 — one fixed LLM call, no branching, no tool-calling loop.
        decision, completion = self.client.chat.completions.create_with_completion(
            model=self.model,
            response_model=WorkflowDecision,
            max_retries=settings.max_retries,
            messages=[
                {"role": "system", "content": WORKFLOW_SYSTEM_PROMPT},
                {"role": "user", "content": _build_user_prompt(claim, chunks)},
            ],
        )
        usage = getattr(completion, "usage_metadata", None)
        prompt_tokens = getattr(usage, "prompt_token_count", 0) or 0
        output_tokens = getattr(usage, "candidates_token_count", 0) or 0
        tokens = prompt_tokens + output_tokens
        cost = (
            (prompt_tokens / 1_000_000) * settings.price_input_per_million
            + (output_tokens / 1_000_000) * settings.price_output_per_million
        )

        # Step 4 — fixed: compute the payout.
        payout_result = compute_payout(decision.claim_status, claim["claimed_amount"], decision.effective_excess_amount)

        elapsed = perf_counter() - started
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
