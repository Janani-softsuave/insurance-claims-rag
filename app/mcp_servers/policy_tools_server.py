from __future__ import annotations

from mcp.server.mcpserver import MCPServer

from app.agent.tools import check_claim_history, compute_payout, get_claim as _get_claim, search_policy

server = MCPServer(name="policy-tools", version="1.0.0")


@server.tool()
def get_claim(claim_number: str) -> dict:
    """Fetch the stored claim record - sum insured, excess amount, claimed amount, and the
    adjuster's raw notes - for one claim by its claim number. Call this first for any claim
    you don't already have data for; every other tool that needs claim details expects you
    to have called this one already. Claim numbers look like CLM-YYYY-nnnnn
    (e.g. CLM-2027-00201) - if the number you were given doesn't look like that, say so
    instead of calling this tool."""
    record = _get_claim(claim_number)
    if "error" in record:
        return {"error": f"claim {claim_number} not found: claim numbers look like CLM-YYYY-nnnnn (e.g. CLM-2027-00201)."}
    return record


@server.tool()
def search_policy_text(query: str, top_k: int = 4) -> list[dict]:
    """Search the insurer's policy wording and endorsement documents for text relevant to a
    described incident or coverage question, and return the most relevant passages. This is
    the only tool that searches policy document text - use it to check whether a peril,
    exclusion, or endorsement applies to what the adjuster notes describe."""
    return search_policy(query, top_k=top_k)


@server.tool()
def compute_claim_payout(claim_status: str, claimed_amount: float, excess_amount: float) -> dict:
    """Compute the payout amount owed for a claim, given a coverage decision you have already
    made and the claimed and excess amounts. This is the only tool that does payout
    arithmetic - it does not fetch claim records or search policy text, and it does not
    decide coverage itself. Call it only after you have already determined claim_status
    from the claim record and any relevant policy text.

    claim_status must be one of: covered, denied, partial, pending.
    covered = fully payable; denied = not payable, an exclusion applies;
    partial = payable at a reduced rate (e.g. a depreciation exception);
    pending = not yet payable, a required document or condition is outstanding.
    excess_amount is usually the claim record's excess_amount, but pass 0 if policy text
    shows the deductible is waived for this specific claim."""
    return compute_payout(claim_status, claimed_amount, excess_amount)


@server.tool()
def check_policy_claim_history(policy_id: str) -> dict:
    """Look up how many claims a policy has already had this policy year, including
    endorsement-specific counts (IMT-28 Zero Dep claims, IMT-40 roadside assistance events),
    so you can check per-year caps such as 'IMT-28 is capped at 2 claims per policy year'.
    This is the only tool that returns claim-frequency history - it does not fetch this
    claim's own details or search policy text."""
    return check_claim_history(policy_id)


@server.tool()
def submit_decision(claim_number: str, claim_status: str, payout: float, rationale: str) -> dict:
    """Submit your final decision for this claim and end the task. Call this exactly once,
    only after you have fetched the claim, checked policy text if needed, and computed the
    payout. This is the task's finish action, not a data tool."""
    return {
        "claim_number": claim_number,
        "claim_status": claim_status,
        "payout": payout,
        "rationale": rationale,
        "final": True,
    }


@server.tool()
def flag_for_review(claim_number: str, reason: str) -> dict:
    """End the task by escalating this claim to a human adjuster instead of deciding it
    yourself, when the claim record and policy text together are not enough to confidently
    determine coverage. Call this exactly once, instead of submit_decision, only when you
    cannot responsibly decide. This is a finish action, not a data tool."""
    return {
        "claim_number": claim_number,
        "claim_status": "flagged_for_review",
        "payout": None,
        "rationale": reason,
        "final": True,
        "flagged": True,
    }


if __name__ == "__main__":
    server.run(transport="stdio")
