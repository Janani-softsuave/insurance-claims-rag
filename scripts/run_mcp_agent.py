from __future__ import annotations

import asyncio
import json
from pathlib import Path

import typer
from rich.console import Console

from app.agent.budgets import Budgets
from app.mcp_agent.agent import MCPAgent

app = typer.Typer(help="Week 9 - run one claim through the MCP client agent.")
console = Console()

BUDGETS = Budgets(max_iterations=8, max_tokens=30_000, max_cost_usd=0.05, max_wall_clock_seconds=90.0)


async def _run(claim_number: str, config_path: Path | None) -> None:
    agent = MCPAgent(budgets=BUDGETS, config_path=config_path)
    specs = await agent.connect()
    console.print(f"Connected to servers: {[s.name for s in specs]}")
    console.print(f"Discovered tools: {agent.discovered_tools()}")

    result = await agent.run(claim_number)
    await agent.close()

    console.print(f"\nstatus={result.status} payout={result.payout} flagged={result.flagged_for_review}")
    console.print("\nTool call trace (name, owning server):")
    for call in result.tool_calls:
        console.print(f"  [{call['server']}] {call['tool']}({call['args']})")

    console.print("\nFull log:")
    for line in result.log:
        console.print(line)


@app.command()
def main(
    claim_number: str = typer.Option("CLM-2027-00201"),
    config: str = typer.Option("mcp_config.json"),
) -> None:
    asyncio.run(_run(claim_number, Path(config)))


if __name__ == "__main__":
    app()
