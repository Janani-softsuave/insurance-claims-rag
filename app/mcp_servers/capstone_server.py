from __future__ import annotations

import re
from time import perf_counter

from mcp.server.mcpserver import MCPServer

from app.agent import capstone_tools
from app.agent.capstone_tools import get_claim as _get_claim, refer_to_adjuster as _refer_to_adjuster
from app.core.tracing import redact
from app.observability.tracing import log_span, new_trace_id

server = MCPServer(name="claims-triage-coverage", version="1.0.0")


@server.tool()
def get_claim(claim_number: str) -> dict:
    """Fetch the stored FNOL/claim record for one claim by its claim number: policy number,
    product, loss date, claimed amount, FNOL text, adjuster notes, photo caption, and the
    policy's deductible/sub-limit/policy-limit figures. Call this first for any claim you
    don't already have data for.

    Returns a trace_id — copy that EXACT value into the trace_id argument of every other tool
    you call for the rest of this claim, so the same request can be traced end to end.

    Adjuster notes and FNOL text are redacted before being returned — claimant names,
    addresses, and anything matching a labelled-name pattern are replaced with placeholders.
    This server never hands claimant PII to a calling agent, regardless of who it is."""
    started = perf_counter()
    record = _get_claim(claim_number)
    trace_id = new_trace_id()
    if "error" in record:
        log_span(trace_id, "mcp_tool", "get_claim", (perf_counter() - started) * 1000, metadata={"error": record["error"]})
        return {"trace_id": trace_id, **record}
    for field in ("fnol_text", "adjuster_notes", "photo_caption"):
        if record.get(field):
            redacted, _ = redact(record[field])
            record[field] = redacted
    log_span(trace_id, "mcp_tool", "get_claim", (perf_counter() - started) * 1000, metadata={"claim_number": claim_number})
    return {"trace_id": trace_id, **record}


@server.tool()
def check_coverage_in_force(trace_id: str, policy_number: str, loss_date: str) -> dict:
    """Check whether the policy's coverage was in force on the loss date. This is the only
    tool that returns the policy's coverage start/end dates — call it before deciding
    anything else, since a lapsed policy on the loss date changes everything downstream.
    trace_id must be the exact value get_claim returned."""
    started = perf_counter()
    result = capstone_tools.check_coverage_in_force(policy_number, loss_date)
    log_span(trace_id, "mcp_tool", "check_coverage_in_force", (perf_counter() - started) * 1000, metadata={"policy_number": policy_number})
    return result


@server.tool()
def search_policy_wording(trace_id: str, query: str, loss_date: str, top_k: int = 4) -> dict:
    """Search the insurer's policy wording and exclusions schedule for text relevant to a
    described loss, SCOPED to the endorsement version in force on the given loss_date — the
    date filter is enforced by this tool itself, not by asking you to pick the right document.
    Always pass the claim's actual loss_date, never today's date. trace_id must be the exact
    value get_claim returned."""
    started = perf_counter()
    result = capstone_tools.search_policy_wording(query, loss_date, top_k)
    log_span(
        trace_id, "retrieval", "search_policy_wording", (perf_counter() - started) * 1000,
        metadata={"loss_date": loss_date, "context_ids": [f"{c['source']}#chunk{c['chunk_index']}" for c in result["chunks"]]},
    )
    return result


@server.tool()
def compute_amounts(trace_id: str, claimed_amount: float, deductible: float, sub_limit: float | None = None) -> dict:
    """Compute the reference payable amount before and after any sub-limit, given the claimed
    amount, deductible, and sub-limit (omit if none applies). Deductible, sub-limit, and policy
    limit must always be reported as three distinct figures — never collapse them into one
    number. This tool does not decide coverage. trace_id must be the exact value get_claim
    returned."""
    started = perf_counter()
    result = capstone_tools.compute_amounts(claimed_amount, deductible, sub_limit)
    log_span(trace_id, "tools", "compute_amounts", (perf_counter() - started) * 1000)
    return result


@server.tool()
def refer_to_adjuster(
    trace_id: str,
    claim_number: str,
    coverage_signal: str,
    cited_clause: str,
    endorsement_version: str,
    loss_date_resolved_against: str,
    deductible: float,
    policy_limit: str,
    summary: str,
    sub_limit: float | None = None,
) -> dict:
    """End the task by referring this claim to a human adjuster with your findings. Call this
    exactly once, last, ALWAYS — this system never states a coverage decision itself, only
    surfaces the facts and cited wording. coverage_signal must be 'supports_coverage',
    'supports_exclusion', or 'ambiguous' — never the word 'covered'. Cite the exact clause AND
    the endorsement version it came from, and the loss_date you resolved it against. trace_id
    must be the exact value get_claim returned."""
    started = perf_counter()
    if coverage_signal not in ("supports_coverage", "supports_exclusion", "ambiguous"):
        log_span(trace_id, "tools", "refer_to_adjuster", (perf_counter() - started) * 1000, metadata={"rejected": "bad coverage_signal"})
        return {
            "final": True,
            "error": f"coverage_signal must be supports_coverage/supports_exclusion/ambiguous, got {coverage_signal!r}",
        }
    if re.search(r"\bcovered\b", summary, re.IGNORECASE):
        log_span(trace_id, "tools", "refer_to_adjuster", (perf_counter() - started) * 1000, metadata={"rejected": "said 'covered'"})
        return {
            "final": True,
            "error": "summary must not state a coverage decision ('covered') — this system refers, it does not decide. Rewrite without that word.",
        }
    result = _refer_to_adjuster(
        claim_number=claim_number,
        coverage_signal=coverage_signal,
        cited_clause=cited_clause,
        endorsement_version=endorsement_version,
        loss_date_resolved_against=loss_date_resolved_against,
        deductible=deductible,
        sub_limit=sub_limit,
        policy_limit=policy_limit,
        summary=summary,
    )
    log_span(trace_id, "tools", "refer_to_adjuster", (perf_counter() - started) * 1000, metadata={"coverage_signal": coverage_signal})
    result["final"] = True
    result["trace_id"] = trace_id
    return result


if __name__ == "__main__":
    server.run(transport="stdio")
