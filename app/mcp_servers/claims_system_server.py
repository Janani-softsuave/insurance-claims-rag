from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from mcp.server.mcpserver import MCPServer

DATA_PATH = Path(__file__).resolve().parents[2] / "analysis" / "week9" / "claims_system_data.json"

server = MCPServer(name="claims-system", version="1.0.0")


@lru_cache
def _store() -> dict:
    return json.loads(DATA_PATH.read_text(encoding="utf-8"))


@server.tool()
def get_claim_status(claim_number: str) -> dict:
    """Look up the current processing status of a claim in the claims-processing system
    (submitted, under_review, settled, denied, or closed). This reflects the live workflow
    state as tracked by claims operations, separate from any coverage decision an assistant
    might compute itself. Claim numbers look like CLM-YYYY-nnnnn."""
    record = _store().get(claim_number)
    if record is None:
        return {"error": f"claim {claim_number} not found: claim numbers look like CLM-YYYY-nnnnn (e.g. CLM-2027-00201)."}
    return {"claim_number": claim_number, "status": record["status"]}


@server.tool()
def get_adjuster_note_history(claim_number: str) -> dict:
    """Return the dated history of adjuster notes logged against a claim in the
    claims-processing system, oldest first. Use this to see how a claim has actually been
    handled over time, not just its current status. Claim numbers look like CLM-YYYY-nnnnn."""
    record = _store().get(claim_number)
    if record is None:
        return {"error": f"claim {claim_number} not found: claim numbers look like CLM-YYYY-nnnnn (e.g. CLM-2027-00201)."}
    return {"claim_number": claim_number, "notes": record["adjuster_notes_history"]}


if __name__ == "__main__":
    server.run(transport="stdio")
