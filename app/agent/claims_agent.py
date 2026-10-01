from __future__ import annotations

import json
from dataclasses import dataclass, field

from google.genai import types

from app.agent.budgets import Budgets, BudgetExceeded, BudgetTracker
from app.agent.llm_client import GeminiKeyRotatingClient
from app.agent.tools import AGENT_TOOLS, TOOL_IMPLS
from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

SYSTEM_PROMPT = """You are a claims triage agent for ABC Insurance.

Given a claim number, decide the claim's status and payout using the tools
available to you:
- get_claim: fetch the claim record (excess, claimed amount, adjuster notes).
- search_policy: search policy text, only if the adjuster notes raise a
  coverage question policy text can answer (an exclusion, an endorsement
  requirement, a pending-document rule). Don't call it if there's no such
  question.
- compute_payout: compute the payout once you've decided claim_status. Pass
  excess_amount=0 instead of the claim record's default excess if policy text
  shows the deductible is waived for this claim.
- check_claim_history: look up how many claims a policy has already had this
  year, only if the endorsement in play has a per-year cap (e.g. IMT-28 is
  capped at 2 claims per policy year, IMT-40 at 4 events per policy year).
- submit_decision: call this exactly once, last, with your final
  claim_number, claim_status, payout, and rationale — only when you're
  confident in the decision.
- flag_for_review: call this instead of submit_decision, exactly once, if the
  claim record and policy text together genuinely aren't enough to decide
  confidently. Don't guess when you should escalate.

Never invent a policy rule not present in what search_policy returns."""

MITIGATED_SYSTEM_PROMPT = SYSTEM_PROMPT.replace(
    "- search_policy: search policy text, only if the adjuster notes raise a\n"
    "  coverage question policy text can answer (an exclusion, an endorsement\n"
    "  requirement, a pending-document rule). Don't call it if there's no such\n"
    "  question.",
    "- search_policy: search policy text, only if the adjuster notes raise a\n"
    "  coverage question policy text can answer (an exclusion, an endorsement\n"
    "  requirement, a pending-document rule). Don't call it if there's no such\n"
    "  question. Call it AT MOST ONCE per claim — one well-formed query that\n"
    "  names the incident type and the endorsement/exclusion in question\n"
    "  returns everything relevant. Re-querying with rephrased text wastes\n"
    "  budget and does not surface new passages.",
).replace(
    "- compute_payout: compute the payout once you've decided claim_status. Pass\n"
    "  excess_amount=0 instead of the claim record's default excess if policy text\n"
    "  shows the deductible is waived for this claim.",
    "- compute_payout: compute the payout once you've decided claim_status. Pass\n"
    "  excess_amount=0 instead of the claim record's default excess if policy text\n"
    "  shows the deductible is waived for this claim. Call it AT MOST ONCE — decide\n"
    "  claim_status and the effective excess_amount BEFORE calling it, don't call it\n"
    "  speculatively to explore alternatives.",
)


@dataclass
class AgentRunResult:
    claim_number: str
    status: str | None
    payout: float | None
    rationale: str | None
    iterations: int
    total_tokens: int
    total_cost_usd: float
    elapsed_seconds: float
    tool_calls: list[str] = field(default_factory=list)
    trajectory: list[dict] = field(default_factory=list)
    terminated_by_budget: str | None = None
    flagged_for_review: bool = False
    log: list[str] = field(default_factory=list)


def _call_cost(usage) -> tuple[int, float]:
    if usage is None:
        return 0, 0.0
    in_tok = getattr(usage, "prompt_token_count", 0) or 0
    out_tok = getattr(usage, "candidates_token_count", 0) or 0
    cost = (in_tok / 1_000_000) * settings.price_input_per_million + (out_tok / 1_000_000) * settings.price_output_per_million
    return in_tok + out_tok, cost


class ClaimsAgent:
    def __init__(
        self,
        budgets: Budgets | None = None,
        api_key: str | None = None,
        model: str | None = None,
        system_prompt: str | None = None,
        tool_impls: dict | None = None,
        output_guardrail=None,
    ):
        self._llm = GeminiKeyRotatingClient(api_key=api_key, model=model)
        self.budgets = budgets or Budgets()
        self.system_prompt = system_prompt or SYSTEM_PROMPT
        self.tool_impls = tool_impls or TOOL_IMPLS
        self.output_guardrail = output_guardrail

    def run(self, claim_number: str) -> AgentRunResult:
        tracker = BudgetTracker(budgets=self.budgets)
        tracker.start()
        log: list[str] = []
        tool_calls: list[str] = []
        trajectory: list[dict] = []

        contents = [types.Content(role="user", parts=[types.Part(text=f"Triage claim {claim_number}.")])]
        config = types.GenerateContentConfig(
            system_instruction=self.system_prompt,
            tools=[AGENT_TOOLS],
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
        )

        final: dict | None = None
        flagged_for_review = False
        terminated_by_budget: str | None = None

        while final is None:
            try:
                tracker.check()
            except BudgetExceeded as exc:
                terminated_by_budget = exc.which
                log.append(f"BUDGET EXCEEDED before iteration {tracker.iterations + 1}: {exc}")
                logger.warning("Agent for %s terminated cleanly: %s", claim_number, exc)
                break

            response = self._llm.generate(contents, config)
            tokens, cost = _call_cost(response.usage_metadata)
            tracker.record_call(tokens=tokens, cost_usd=cost)

            candidate = response.candidates[0]
            contents.append(candidate.content)

            function_calls = [p.function_call for p in candidate.content.parts if p.function_call]
            if not function_calls:
                log.append(f"iter {tracker.iterations}: model returned no tool call — stopping without a decision.")
                break

            response_parts = []
            for fc in function_calls:
                name = fc.name
                args = dict(fc.args or {})
                tool_calls.append(name)

                if name == "submit_decision":
                    rejection = self.output_guardrail(args) if self.output_guardrail else None
                    if rejection:
                        trajectory.append({"tool": name, "args": args, "result": {"rejected": rejection}})
                        log.append(f"iter {tracker.iterations}: submit_decision REJECTED by guardrail -> {rejection}")
                        response_parts.append(
                            types.Part(
                                function_response=types.FunctionResponse(
                                    name=name,
                                    response={"result": {"error": f"submit_decision rejected: {rejection}. Reconsider, or call flag_for_review if you cannot proceed."}},
                                )
                            )
                        )
                        continue
                    final = args
                    trajectory.append({"tool": name, "args": args, "result": None})
                    log.append(f"iter {tracker.iterations}: submit_decision -> {args}")
                    break

                if name == "flag_for_review":
                    flagged_for_review = True
                    final = {
                        "claim_number": args.get("claim_number", claim_number),
                        "claim_status": "flagged_for_review",
                        "payout": None,
                        "rationale": args.get("reason"),
                    }
                    trajectory.append({"tool": name, "args": args, "result": None})
                    log.append(f"iter {tracker.iterations}: flag_for_review -> {args}")
                    break

                impl = self.tool_impls.get(name)
                result = {"error": f"unknown tool {name}"} if impl is None else impl(**args)
                trajectory.append({"tool": name, "args": args, "result": result})
                log.append(f"iter {tracker.iterations}: {name}({args}) -> {json.dumps(result, default=str)[:300]}")
                response_parts.append(types.Part(function_response=types.FunctionResponse(name=name, response={"result": result})))

            if final is not None:
                break
            contents.append(types.Content(role="user", parts=response_parts))

        return AgentRunResult(
            claim_number=claim_number,
            status=final.get("claim_status") if final else None,
            payout=final.get("payout") if final else None,
            rationale=final.get("rationale") if final else None,
            iterations=tracker.iterations,
            total_tokens=tracker.total_tokens,
            total_cost_usd=tracker.total_cost_usd,
            elapsed_seconds=tracker.elapsed_seconds,
            tool_calls=tool_calls,
            trajectory=trajectory,
            terminated_by_budget=terminated_by_budget,
            flagged_for_review=flagged_for_review,
            log=log,
        )
