from __future__ import annotations

import asyncio
import json

import typer
from rich.console import Console

from app.agent.capstone_prompt import CAPSTONE_SYSTEM_PROMPT
from app.agent.budgets import Budgets
from app.core.config import ROOT_DIR
from app.mcp_agent.agent import MCPAgent

app = typer.Typer(help="Week 12 Capstone — Claims Triage & Coverage Assistant. One command, one entry point.")
console = Console()

CAPSTONE_CONFIG_PATH = ROOT_DIR / "mcp_config.capstone.json"
CAPSTONE_BUDGETS = Budgets(max_iterations=8, max_tokens=30_000, max_cost_usd=0.05, max_wall_clock_seconds=120.0)


async def _triage(claim_number: str) -> None:
    agent = MCPAgent(budgets=CAPSTONE_BUDGETS, system_prompt=CAPSTONE_SYSTEM_PROMPT, config_path=CAPSTONE_CONFIG_PATH)
    await agent.connect()
    console.print(f"[dim]discovered tools:[/dim] {list(agent.discovered_tools().keys())}")
    try:
        result = await agent.run(claim_number)
    finally:
        await agent.close()

    console.print(f"\n[bold]trace_id:[/bold] {result.trace_id}")
    console.print(f"[bold]iterations:[/bold] {result.iterations}  [bold]tokens:[/bold] {result.total_tokens}  [bold]cost:[/bold] ${result.total_cost_usd:.6f}")
    console.print("\n[bold]tool calls:[/bold]")
    for tc in result.tool_calls:
        console.print(f"  [{tc['server']}] {tc['tool']}({tc['args']})")
    console.print("\n[bold]final (referral, not a decision):[/bold]")
    console.print(json.dumps(result.final, indent=2, ensure_ascii=False))
    if result.terminated_by_budget:
        console.print(f"[red]terminated by budget: {result.terminated_by_budget}[/red]")


@app.command()
def triage(claim_number: str = typer.Argument(..., help="e.g. CLM-2027-00310")) -> None:
    """Triage one claim end to end: MCP-discovered tools, loss-date-scoped retrieval,
    coverage-in-force check, referral to an adjuster — never a coverage decision."""
    asyncio.run(_triage(claim_number))


if __name__ == "__main__":
    app()
