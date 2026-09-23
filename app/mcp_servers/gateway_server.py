from __future__ import annotations

import json
import os
import sys
import time
from contextlib import AsyncExitStack, asynccontextmanager
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.server.mcpserver import MCPServer

ROOT_DIR = Path(__file__).resolve().parents[2]
AUDIT_LOG_PATH = ROOT_DIR / "analysis" / "week9" / "audit.log"

TOKEN_SCOPES = {
    "full": frozenset(),
    "claims-status-only": frozenset({"get_adjuster_note_history"}),
}

_sessions: dict[str, ClientSession] = {}


@asynccontextmanager
async def lifespan(_server: MCPServer):
    stack = AsyncExitStack()
    backends = [
        ("policy-tools", ["-m", "app.mcp_servers.policy_tools_server"]),
        ("claims-system", ["-m", "app.mcp_servers.claims_system_server"]),
    ]
    for _name, args in backends:
        params = StdioServerParameters(command=sys.executable, args=args, cwd=str(ROOT_DIR))
        read, write = await stack.enter_async_context(stdio_client(params))
        session = await stack.enter_async_context(ClientSession(read, write))
        await session.initialize()
        listed = await session.list_tools()
        for tool in listed.tools:
            _sessions[tool.name] = session
    try:
        yield {}
    finally:
        await stack.aclose()


server = MCPServer(name="claims-gateway", version="1.0.0", lifespan=lifespan)


def _token() -> str:
    return os.environ.get("GATEWAY_TOKEN", "full")


def _audit(caller: str, tool: str, args: dict, allowed: bool) -> None:
    AUDIT_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    claim_number = args.get("claim_number", "")
    line = f"{time.strftime('%Y-%m-%dT%H:%M:%S')} | caller={caller} | tool={tool} | claim_number={claim_number} | allowed={allowed}\n"
    with AUDIT_LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(line)


async def _proxy(name: str, args: dict) -> dict:
    caller = _token()
    denied = TOKEN_SCOPES.get(caller, TOKEN_SCOPES["full"])
    if name in denied:
        _audit(caller, name, args, allowed=False)
        return {
            "error": f"tool '{name}' denied for token scope '{caller}': this token is limited to claim-status lookups, adjuster notes require a different token."
        }
    _audit(caller, name, args, allowed=True)
    result = await _sessions[name].call_tool(name, args)
    if result.structured_content is not None:
        return result.structured_content
    text = "".join(block.text for block in result.content if hasattr(block, "text"))
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {"result": text}


@server.tool()
async def get_claim(claim_number: str) -> dict:
    """Fetch the stored claim record - sum insured, excess amount, claimed amount, and the
    adjuster's raw notes - for one claim by its claim number. Call this first for any claim
    you don't already have data for. Claim numbers look like CLM-YYYY-nnnnn."""
    return await _proxy("get_claim", {"claim_number": claim_number})


@server.tool()
async def search_policy_text(query: str, top_k: int = 4) -> dict:
    """Search the insurer's policy wording and endorsement documents for text relevant to a
    described incident or coverage question, and return the most relevant passages."""
    return await _proxy("search_policy_text", {"query": query, "top_k": top_k})


@server.tool()
async def compute_claim_payout(claim_status: str, claimed_amount: float, excess_amount: float) -> dict:
    """Compute the payout amount owed for a claim, given a coverage decision you have already
    made and the claimed and excess amounts. claim_status must be one of: covered, denied,
    partial, pending."""
    return await _proxy(
        "compute_claim_payout",
        {"claim_status": claim_status, "claimed_amount": claimed_amount, "excess_amount": excess_amount},
    )


@server.tool()
async def check_policy_claim_history(policy_id: str) -> dict:
    """Look up how many claims a policy has already had this policy year, including
    endorsement-specific counts (IMT-28, IMT-40)."""
    return await _proxy("check_policy_claim_history", {"policy_id": policy_id})


@server.tool()
async def get_claim_status(claim_number: str) -> dict:
    """Look up the current processing status of a claim in the claims-processing system
    (submitted, under_review, settled, denied, or closed). Claim numbers look like
    CLM-YYYY-nnnnn."""
    return await _proxy("get_claim_status", {"claim_number": claim_number})


@server.tool()
async def get_adjuster_note_history(claim_number: str) -> dict:
    """Return the dated history of adjuster notes logged against a claim in the
    claims-processing system, oldest first. Claim numbers look like CLM-YYYY-nnnnn."""
    return await _proxy("get_adjuster_note_history", {"claim_number": claim_number})


@server.tool()
async def submit_decision(claim_number: str, claim_status: str, payout: float, rationale: str) -> dict:
    """Submit your final decision for this claim and end the task. Call this exactly once,
    only after you have fetched the claim, checked policy text if needed, and computed the
    payout."""
    return await _proxy(
        "submit_decision",
        {"claim_number": claim_number, "claim_status": claim_status, "payout": payout, "rationale": rationale},
    )


@server.tool()
async def flag_for_review(claim_number: str, reason: str) -> dict:
    """End the task by escalating this claim to a human adjuster instead of deciding it
    yourself, when the information available genuinely isn't enough to decide confidently."""
    return await _proxy("flag_for_review", {"claim_number": claim_number, "reason": reason})


if __name__ == "__main__":
    server.run(transport="stdio")
