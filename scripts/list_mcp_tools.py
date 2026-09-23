from __future__ import annotations

import asyncio
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from app.mcp_agent.agent import MCPAgent

app = typer.Typer(help="Week 9 - list tools discovered via MCP tools/list, from config.")
console = Console()


async def _discover(config_path: Path | None) -> dict[str, str]:
    agent = MCPAgent(config_path=config_path)
    await agent.connect()
    tools = agent.discovered_tools()
    await agent.close()
    return tools


@app.command()
def main(config: str = typer.Option("mcp_config.json", help="Path to the MCP client config file.")) -> None:
    config_path = Path(config)
    tools = asyncio.run(_discover(config_path))

    table = Table(title=f"Tools discovered via tools/list ({config_path})")
    table.add_column("Tool name")
    table.add_column("Server")
    for name, server in sorted(tools.items()):
        table.add_row(name, server)
    console.print(table)
    console.print(f"\n{len(tools)} tool(s) discovered.")


if __name__ == "__main__":
    app()
