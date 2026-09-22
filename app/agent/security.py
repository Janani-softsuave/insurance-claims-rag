from __future__ import annotations

import re

INJECTION_PATTERNS = [
    re.compile(r"ignore (all )?(previous|prior|the above) instructions", re.IGNORECASE),
    re.compile(r"disregard (all )?(previous|prior|the above)", re.IGNORECASE),
    re.compile(r"settle (this|the) claim in full", re.IGNORECASE),
    re.compile(r"no exclusions? appl(y|ies)", re.IGNORECASE),
    re.compile(r"as (instructed|directed) (by|in) (the|this) note", re.IGNORECASE),
]


def sanitize_text(text: str) -> tuple[str, list[str]]:
    removed: list[str] = []
    sanitized = text
    for pattern in INJECTION_PATTERNS:
        removed.extend(m.group(0) for m in pattern.finditer(sanitized))
        sanitized = pattern.sub("[redacted: suspected embedded instruction]", sanitized)
    return sanitized, removed


def settle_instruction_guardrail(args: dict) -> str | None:
    rationale = args.get("rationale") or ""
    for pattern in INJECTION_PATTERNS:
        if pattern.search(rationale):
            return f"rationale echoes a suspected injected instruction (matched {pattern.pattern!r})"
    return None


class GuardedPayout:
    """Least-privilege wrapper: a zero-excess (deductible waiver) payout is only granted
    once search_policy has actually been consulted in this run, not on the model's say-so."""

    def __init__(self, compute_payout_impl, search_policy_impl):
        self._compute_payout_impl = compute_payout_impl
        self._search_policy_impl = search_policy_impl
        self.search_policy_called = False

    def search_policy(self, query: str, top_k: int = 4):
        self.search_policy_called = True
        return self._search_policy_impl(query, top_k=top_k)

    def compute_payout(self, claim_status: str, claimed_amount: float, excess_amount: float) -> dict:
        if excess_amount == 0 and not self.search_policy_called:
            return {
                "error": (
                    "compute_payout refused: a zero-excess (deductible waiver) payout requires a "
                    "prior search_policy call grounding the waiver in policy text."
                )
            }
        return self._compute_payout_impl(claim_status=claim_status, claimed_amount=claimed_amount, excess_amount=excess_amount)
