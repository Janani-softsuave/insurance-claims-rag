from __future__ import annotations

import json
from contextlib import AsyncExitStack
from dataclasses import dataclass, field
from pathlib import Path

from google import genai
from google.genai import types as genai_types
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from app.agent.budgets import Budgets, BudgetExceeded, BudgetTracker
from app.core.config import ROOT_DIR, settings
from app.core.logging import get_logger
from app.mcp_agent.config import ServerSpec, load_server_specs

logger = get_logger(__name__)

SYSTEM_PROMPT = """You are a claims triage agent for ABC Insurance.

Given a claim number, decide the claim's status and payout using whichever
tools are available to you. Read each tool's description before deciding
whether it applies. If a tool exists for checking the claim's current
processing status in the claims-processing system, check it before you
finalize your own coverage decision, so you know whether the claim is
already closed elsewhere. Call submit_decision exactly once, last, with your
final claim_number, claim_status, payout, and rationale - only when you are
confident in the decision. Call flag_for_review instead, exactly once, if the
information available genuinely isn't enough to decide confidently.

Never invent a fact not returned by one of your tools."""


@dataclass
class MCPAgentRunResult:
    claim_number: str
    status: str | None
    payout: float | None
    rationale: str | None
    iterations: int
    total_tokens: int
    total_cost_usd: float
    tool_calls: list[dict] = field(default_factory=list)
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


class MCPAgent:
    def __init__(
        self,
        budgets: Budgets | None = None,
        api_key: str | None = None,
        model: str | None = None,
        system_prompt: str | None = None,
        config_path: Path | None = None,
    ):
        self.client = genai.Client(api_key=api_key or settings.gemini_api_key)
        self.model = model or settings.gemini_model
        self.budgets = budgets or Budgets()
        self.system_prompt = system_prompt or SYSTEM_PROMPT
        self.config_path = config_path
        self._stack: AsyncExitStack | None = None
        self._sessions: dict[str, ClientSession] = {}
        self._tool_owner: dict[str, str] = {}
        self._declarations: list[genai_types.FunctionDeclaration] = []

    async def connect(self) -> list[ServerSpec]:
        self._stack = AsyncExitStack()
        specs = load_server_specs(self.config_path)
        for spec in specs:
            params = StdioServerParameters(command=spec.command, args=spec.args, cwd=str(ROOT_DIR), env=spec.env or None)
            read, write = await self._stack.enter_async_context(stdio_client(params))
            session = await self._stack.enter_async_context(ClientSession(read, write))
            await session.initialize()
            listed = await session.list_tools()
            for tool in listed.tools:
                self._tool_owner[tool.name] = spec.name
                self._sessions[tool.name] = session
                self._declarations.append(
                    genai_types.FunctionDeclaration(
                        name=tool.name,
                        description=tool.description or "",
                        parameters=tool.input_schema,
                    )
                )
        return specs

    async def close(self) -> None:
        if self._stack is not None:
            await self._stack.aclose()

    def discovered_tools(self) -> dict[str, str]:
        return dict(self._tool_owner)

    async def _call_tool(self, name: str, args: dict) -> dict:
        session = self._sessions[name]
        result = await session.call_tool(name, args)
        if result.structured_content is not None:
            return result.structured_content
        text = "".join(block.text for block in result.content if hasattr(block, "text"))
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return {"result": text}

    async def run(self, claim_number: str) -> MCPAgentRunResult:
        tracker = BudgetTracker(budgets=self.budgets)
        tracker.start()
        log: list[str] = []
        tool_calls: list[dict] = []

        contents = [genai_types.Content(role="user", parts=[genai_types.Part(text=f"Triage claim {claim_number}.")])]
        config = genai_types.GenerateContentConfig(
            system_instruction=self.system_prompt,
            tools=[genai_types.Tool(function_declarations=self._declarations)],
            automatic_function_calling=genai_types.AutomaticFunctionCallingConfig(disable=True),
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
                break

            response = self.client.models.generate_content(model=self.model, contents=contents, config=config)
            tokens, cost = _call_cost(response.usage_metadata)
            tracker.record_call(tokens=tokens, cost_usd=cost)

            candidate = response.candidates[0]
            contents.append(candidate.content)

            function_calls = [p.function_call for p in candidate.content.parts if p.function_call]
            if not function_calls:
                log.append(f"iter {tracker.iterations}: model returned no tool call - stopping without a decision.")
                break

            response_parts = []
            for fc in function_calls:
                name = fc.name
                args = dict(fc.args or {})
                owner = self._tool_owner.get(name, "unknown")
                tool_calls.append({"tool": name, "server": owner, "args": args})

                result = await self._call_tool(name, args)
                log.append(f"iter {tracker.iterations}: [{owner}] {name}({args}) -> {json.dumps(result, default=str)[:300]}")

                if result.get("final"):
                    final = result
                    flagged_for_review = bool(result.get("flagged"))
                    break

                response_parts.append(
                    genai_types.Part(function_response=genai_types.FunctionResponse(name=name, response={"result": result}))
                )

            if final is not None:
                break
            contents.append(genai_types.Content(role="user", parts=response_parts))

        return MCPAgentRunResult(
            claim_number=claim_number,
            status=final.get("claim_status") if final else None,
            payout=final.get("payout") if final else None,
            rationale=final.get("rationale") if final else None,
            iterations=tracker.iterations,
            total_tokens=tracker.total_tokens,
            total_cost_usd=tracker.total_cost_usd,
            tool_calls=tool_calls,
            terminated_by_budget=terminated_by_budget,
            flagged_for_review=flagged_for_review,
            log=log,
        )
