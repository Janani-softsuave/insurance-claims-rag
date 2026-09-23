# Week 9 — MCP (Track D, Insurance Claims)

All evidence below is from real runs (`scripts/run_mcp_agent.py`, `scripts/capture_wire.py`,
`scripts/list_mcp_tools.py`) against real local MCP servers over real stdio JSON-RPC, and real
Gemini API calls. Nothing here is fabricated.

## 1. Config-only server swap (30 pts)

`app/mcp_agent/agent.py` never names a tool or server - it loads whatever `mcp_config.json`
lists, connects to each over stdio, and builds its Gemini function declarations from
`tools/list`. Adding the `claims-system` server (`app/mcp_servers/claims_system_server.py`)
was a two-line addition to `mcp_config.json` (`analysis/week9/config_diff.txt`) and nothing
else.

**Proof:** `analysis/week9/agent_diff.txt` is `git diff <before> <after> -- app/mcp_agent/`
between the commit with server one only and the commit with server one + two - **0 lines**.

## 2. Tool counts, from `tools/list` (15 pts)

**6 -> 8** (`analysis/week9/tool_counts.md`, full names and owning server there):

- Before: `check_policy_claim_history`, `compute_claim_payout`, `flag_for_review`,
  `get_claim`, `search_policy_text`, `submit_decision` - all `policy-tools`.
- After: the same six, plus `get_claim_status` and `get_adjuster_note_history`, both
  `claims-system`.

## 3. Raw JSON-RPC exchange, annotated (25 pts)

`analysis/week9/wire.json` - captured with a hand-rolled stdio client
(`scripts/capture_wire.py`) that speaks newline-delimited JSON-RPC 2.0 directly to the
`claims-system` server subprocess, no SDK client wrapper. `analysis/week9/wire_annotated.md`
walks every top-level field of `initialize` -> `notifications/initialized` -> `tools/list` ->
`tools/call`.

**Where the model runs, in one line:** the model is never called anywhere in the JSON-RPC
exchange itself - every message in `wire.json` is a plain client/server round trip; the model
only enters one layer up, inside `agent.py`'s loop, where `generate_content()` decides *which*
tool to call and *what* to pass it, and the client then issues the `tools/call` request shown
in the wire trace - the server executing it has no idea an LLM was involved.

## 4. One query, provably calling server two (part of the 30 pts above, evidenced live)

`analysis/week9/query_trace.md` - a real run against `CLM-2027-00201` shows the tool call
trace calling `get_claim` (`policy-tools`), then `get_claim_status` and
`get_adjuster_note_history` (both `claims-system`), then `search_policy_text`
(`policy-tools`) - discovered tool names from both servers interleaved in one agent run,
following the system prompt's instruction to check claims-system status before finalizing.
The run hit the wall-clock budget before `submit_decision` on this memory-constrained
machine (reranker load + 3 tool round-trips + a Gemini call), reported honestly rather than
hidden - it doesn't affect the discovery proof, which is the tool call trace itself.

## 5. Docstring-as-prompt + recoverable error (20 pts)

`get_claim` on `policy-tools`: before, `"Look up a claim."` plus
`{"error": "Error: lookup failed"}` (the exact anti-pattern the task brief calls out). After,
a docstring written as an instruction (what it does, when to call it, what a valid claim
number looks like) and an error that says *why* the lookup failed and *what a valid claim
number looks like*, matching the style `claims-system`'s tools already used.

Full before/after transcripts, same failing call (`CLM-2024-88120`) both times:
`analysis/week9/error_before_after.md`. Real, measured difference: **before**, the model made
3 failed lookups (`get_claim`, then both `claims-system` tools) chasing the same bad number
because `get_claim`'s own error told it nothing useful; **after**, one call to `get_claim` was
enough - the model didn't need the other two tools, because the error itself already carried
the information it needed.

## 6. Supply-chain risk note (10 pts)

`analysis/week9/risk_note.md` - 5 lines: who wrote `claims-system`, what it can reach
(claim status + adjuster notes, potentially production-scale in a real deployment), what it
logs (unknown - it's not our code), what a stolen token could read (sensitive free-text notes
across every claim number an attacker enumerates), and a scoped-not-as-is ship decision.

## What wasn't attempted

The bonus (single gateway process fronting both servers, one audit line per `tools/call`,
scoped token denying the adjuster-note tool while claim-status still works) was not built in
this pass - the six required deliverables above were the priority given the session's
recurring memory/quota constraints. Happy to build it as a follow-up if wanted.

## Files

| Deliverable | Path |
|---|---|
| Agent module diff (0 lines) | `analysis/week9/agent_diff.txt` |
| Config diff | `analysis/week9/config_diff.txt` |
| Tool counts before -> after | `analysis/week9/tool_counts.md` |
| Raw wire capture | `analysis/week9/wire.json` |
| Wire annotations | `analysis/week9/wire_annotated.md` |
| Query trace (server-two proof) | `analysis/week9/query_trace.md` |
| Error before/after transcript | `analysis/week9/error_before_after.md` |
| Risk note | `analysis/week9/risk_note.md` |
| Server one (ours) | `app/mcp_servers/policy_tools_server.py` |
| Server two (simulated third party) | `app/mcp_servers/claims_system_server.py` |
| MCP client agent | `app/mcp_agent/agent.py`, `app/mcp_agent/config.py` |
| Client config | `mcp_config.json` |
