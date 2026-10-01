from __future__ import annotations

import json
from dataclasses import dataclass, field
from time import perf_counter

from google.genai import types

from app.agent.llm_client import GeminiKeyRotatingClient
from app.agent.tools import (
    CHECK_CLAIM_HISTORY_DECLARATION,
    COMPUTE_PAYOUT_DECLARATION,
    SEARCH_POLICY_DECLARATION,
    check_claim_history,
    compute_payout,
    get_claim,
    search_policy,
)
from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

EXCLUSIONS_WORKER_SYSTEM_PROMPT = """You are the coverage/exclusions specialist on an insurance
claims triage team. You receive one claim's record and must decide ONLY whether an exclusion or
endorsement requirement blocks or limits coverage.

- search_policy: search policy text for the exclusion, endorsement, or waiting-period rule that
  applies to this claim's peril. Call it at most twice.

Respond with your finding as plain text in this exact shape, nothing else:
COVERAGE_OPINION: <covered|denied|partial|pending>
EXCLUSION_OR_ENDORSEMENT: <the specific policy rule that applies, or "none found">
CITED_TEXT: <the policy passage you relied on, or "none">

You do not compute payout amounts and you do not see the adjuster's free-text notes beyond what
is given below — that is the other specialist's job."""

SUMMARY_WORKER_SYSTEM_PROMPT = """You are the adjuster-note summary specialist on an insurance
claims triage team. You receive one claim's record and must extract the structured facts a
decision-maker needs, without deciding coverage yourself.

- check_claim_history: look up how many claims the policy has already had this policy year, only
  if the adjuster notes mention an endorsement with a per-year cap (IMT-28, IMT-40). Call it at
  most once.

Respond with your finding as plain text in this exact shape, nothing else:
INCIDENT_SUMMARY: <one sentence, what happened>
ENDORSEMENT_OR_CAP_FLAGS: <any endorsement or per-year cap relevant, or "none">
CLAIM_HISTORY_NOTE: <what check_claim_history returned, or "not checked">

You do not search policy text and you do not decide coverage — that is the other specialist's
job."""

SYNTHESIS_SYSTEM_PROMPT = """You are the manager on an insurance claims triage team. Two
specialists have reported back on one claim: the coverage/exclusions specialist and the
adjuster-note summary specialist. Reconcile their findings into one final decision.

- compute_payout: compute the payout once you've decided claim_status. Pass excess_amount=0
  instead of the claim record's default excess if the exclusions specialist's finding shows the
  deductible is waived.
- submit_decision: call this exactly once, last, with your final claim_number, claim_status,
  payout, and rationale — only when you're confident in the decision.
- flag_for_review: call this instead of submit_decision, exactly once, if the two specialists'
  findings together genuinely aren't enough to decide confidently, or if a specialist's finding
  is missing or unavailable — do not guess coverage when a specialist could not report.

Never invent a policy rule not present in the exclusions specialist's finding. If the
coverage/exclusions specialist's opinion says "denied" or "partial", do not round that up to
"covered" in your own decision."""

_EXCLUSIONS_TOOLS = types.Tool(function_declarations=[SEARCH_POLICY_DECLARATION])
_SUMMARY_TOOLS = types.Tool(function_declarations=[CHECK_CLAIM_HISTORY_DECLARATION])
_SYNTHESIS_TOOLS = types.Tool(
    function_declarations=[
        COMPUTE_PAYOUT_DECLARATION,
        types.FunctionDeclaration(
            name="submit_decision",
            description="Submit the final decision for this claim and end the task.",
            parameters={
                "type": "object",
                "properties": {
                    "claim_number": {"type": "string"},
                    "claim_status": {"type": "string", "enum": ["covered", "denied", "partial", "pending"]},
                    "payout": {"type": "number"},
                    "rationale": {"type": "string"},
                },
                "required": ["claim_number", "claim_status", "payout", "rationale"],
            },
        ),
        types.FunctionDeclaration(
            name="flag_for_review",
            description="Escalate this claim to a human adjuster instead of deciding it.",
            parameters={
                "type": "object",
                "properties": {
                    "claim_number": {"type": "string"},
                    "reason": {"type": "string"},
                },
                "required": ["claim_number", "reason"],
            },
        ),
    ]
)


class WorkerFailure(Exception):
    def __init__(self, worker: str, detail: str):
        self.worker = worker
        self.detail = detail
        super().__init__(f"{worker} failed: {detail}")


def _call_cost(usage) -> tuple[int, int, float]:
    if usage is None:
        return 0, 0, 0.0
    in_tok = getattr(usage, "prompt_token_count", 0) or 0
    out_tok = getattr(usage, "candidates_token_count", 0) or 0
    cost = (in_tok / 1_000_000) * settings.price_input_per_million + (out_tok / 1_000_000) * settings.price_output_per_million
    return in_tok, out_tok, cost


@dataclass
class HandOff:
    label: str
    claim_number: str
    prompt_tokens: int
    output_tokens: int
    total_tokens: int
    cost_usd: float


@dataclass
class OrchestratorRunResult:
    claim_number: str
    status: str | None
    payout: float | None
    rationale: str | None
    total_tokens: int
    total_cost_usd: float
    elapsed_seconds: float
    tool_calls: list[str] = field(default_factory=list)
    handoffs: list[HandOff] = field(default_factory=list)
    flagged_for_review: bool = False
    worker_failure: str | None = None
    log: list[str] = field(default_factory=list)


class ClaimsOrchestrator:
    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        inject_exclusions_failure_for: str | None = None,
    ):
        self._llm = GeminiKeyRotatingClient(api_key=api_key, model=model)
        self.inject_exclusions_failure_for = inject_exclusions_failure_for

    def _generate(self, system_prompt: str, user_prompt: str, tools: types.Tool | None, tool_impls: dict, max_tool_iters: int = 4):
        contents = [types.Content(role="user", parts=[types.Part(text=user_prompt)])]
        config = types.GenerateContentConfig(
            system_instruction=system_prompt,
            tools=[tools] if tools else None,
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True) if tools else None,
        )
        prompt_tokens = 0
        output_tokens = 0
        cost = 0.0
        tool_calls: list[str] = []
        text = ""

        for _ in range(max_tool_iters):
            response = self._llm.generate(contents, config)
            in_tok, out_tok, call_cost = _call_cost(response.usage_metadata)
            prompt_tokens += in_tok
            output_tokens += out_tok
            cost += call_cost

            candidate = response.candidates[0]
            contents.append(candidate.content)

            function_calls = [p.function_call for p in candidate.content.parts if p.function_call]
            if not function_calls:
                text = "".join(p.text or "" for p in candidate.content.parts)
                break

            response_parts = []
            for fc in function_calls:
                name = fc.name
                args = dict(fc.args or {})
                tool_calls.append(name)
                impl = tool_impls.get(name)
                result = {"error": f"unknown tool {name}"} if impl is None else impl(**args)
                response_parts.append(types.Part(function_response=types.FunctionResponse(name=name, response={"result": result})))
            contents.append(types.Content(role="user", parts=response_parts))

        return text, tool_calls, prompt_tokens, output_tokens, cost

    def _run_exclusions_worker(self, claim: dict, log: list[str], handoffs: list[HandOff]) -> str:
        claim_number = claim["claim_number"]
        user_prompt = f"CLAIM RECORD:\n{json.dumps(claim)}\n\nReport your finding now."

        if self.inject_exclusions_failure_for == claim_number:
            attempts = 0
            while attempts < 2:
                attempts += 1
                log.append(f"manager -> exclusions worker (attempt {attempts}): injected 500 (simulated upstream failure)")
                if attempts >= 2:
                    raise WorkerFailure("exclusions worker", "upstream returned 500 twice (injected fault) — not recoverable via retry")
            return ""

        text, tool_calls, in_tok, out_tok, cost = self._generate(
            EXCLUSIONS_WORKER_SYSTEM_PROMPT, user_prompt, _EXCLUSIONS_TOOLS, {"search_policy": search_policy}
        )
        handoffs.append(HandOff("manager -> exclusions worker", claim_number, in_tok, out_tok, in_tok + out_tok, cost))
        log.append(f"exclusions worker tool_calls={tool_calls} -> {text.strip()[:300]}")
        return text

    def _run_summary_worker(self, claim: dict, log: list[str], handoffs: list[HandOff]) -> str:
        claim_number = claim["claim_number"]
        user_prompt = f"CLAIM RECORD:\n{json.dumps(claim)}\n\nReport your finding now."
        text, tool_calls, in_tok, out_tok, cost = self._generate(
            SUMMARY_WORKER_SYSTEM_PROMPT, user_prompt, _SUMMARY_TOOLS, {"check_claim_history": check_claim_history}
        )
        handoffs.append(HandOff("manager -> summary worker", claim_number, in_tok, out_tok, in_tok + out_tok, cost))
        log.append(f"summary worker tool_calls={tool_calls} -> {text.strip()[:300]}")
        return text

    def run(self, claim_number: str) -> OrchestratorRunResult:
        started = perf_counter()
        log: list[str] = []
        handoffs: list[HandOff] = []
        tool_calls: list[str] = []

        claim = get_claim(claim_number)
        log.append(f"manager: fetched claim record for {claim_number}")

        try:
            exclusions_finding = self._run_exclusions_worker(claim, log, handoffs)
        except WorkerFailure as exc:
            log.append(f"manager: exclusions worker unrecoverable ({exc.detail}) — degrading to flag_for_review, NOT guessing coverage")
            elapsed = perf_counter() - started
            total_tokens = sum(h.total_tokens for h in handoffs)
            total_cost = sum(h.cost_usd for h in handoffs)
            return OrchestratorRunResult(
                claim_number=claim_number,
                status="flagged_for_review",
                payout=None,
                rationale=f"exclusions/coverage check unavailable ({exc.detail}); escalating rather than deciding coverage without it.",
                total_tokens=total_tokens,
                total_cost_usd=total_cost,
                elapsed_seconds=elapsed,
                tool_calls=tool_calls,
                handoffs=handoffs,
                flagged_for_review=True,
                worker_failure=exc.detail,
                log=log,
            )

        summary_finding = self._run_summary_worker(claim, log, handoffs)

        synthesis_prompt = (
            f"CLAIM RECORD:\n{json.dumps(claim)}\n\n"
            f"EXCLUSIONS SPECIALIST FINDING:\n{exclusions_finding}\n\n"
            f"SUMMARY SPECIALIST FINDING:\n{summary_finding}\n\n"
            "Decide now."
        )

        final: dict | None = None
        flagged_for_review = False

        contents = [types.Content(role="user", parts=[types.Part(text=synthesis_prompt)])]
        config = types.GenerateContentConfig(
            system_instruction=SYNTHESIS_SYSTEM_PROMPT,
            tools=[_SYNTHESIS_TOOLS],
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
        )

        for _ in range(4):
            response = self._llm.generate(contents, config)
            in_tok, out_tok, cost = _call_cost(response.usage_metadata)
            handoffs.append(HandOff("workers -> manager synthesis", claim_number, in_tok, out_tok, in_tok + out_tok, cost))

            candidate = response.candidates[0]
            contents.append(candidate.content)

            function_calls = [p.function_call for p in candidate.content.parts if p.function_call]
            if not function_calls:
                log.append("manager synthesis: model returned no tool call — stopping without a decision.")
                break

            response_parts = []
            for fc in function_calls:
                name = fc.name
                args = dict(fc.args or {})
                tool_calls.append(name)

                if name == "submit_decision":
                    final = args
                    log.append(f"manager synthesis: submit_decision -> {args}")
                    break
                if name == "flag_for_review":
                    flagged_for_review = True
                    final = {
                        "claim_number": args.get("claim_number", claim_number),
                        "claim_status": "flagged_for_review",
                        "payout": None,
                        "rationale": args.get("reason"),
                    }
                    log.append(f"manager synthesis: flag_for_review -> {args}")
                    break

                impl = {"compute_payout": compute_payout}.get(name)
                result = {"error": f"unknown tool {name}"} if impl is None else impl(**args)
                log.append(f"manager synthesis: {name}({args}) -> {result}")
                response_parts.append(types.Part(function_response=types.FunctionResponse(name=name, response={"result": result})))

            if final is not None:
                break
            contents.append(types.Content(role="user", parts=response_parts))

        elapsed = perf_counter() - started
        total_tokens = sum(h.total_tokens for h in handoffs)
        total_cost = sum(h.cost_usd for h in handoffs)

        return OrchestratorRunResult(
            claim_number=claim_number,
            status=final.get("claim_status") if final else None,
            payout=final.get("payout") if final else None,
            rationale=final.get("rationale") if final else None,
            total_tokens=total_tokens,
            total_cost_usd=total_cost,
            elapsed_seconds=elapsed,
            tool_calls=tool_calls,
            handoffs=handoffs,
            flagged_for_review=flagged_for_review,
            log=log,
        )
