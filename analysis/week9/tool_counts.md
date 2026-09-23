# Tool discovery counts (from MCP `tools/list`, not hand-written)

## Before — `mcp_config.json` with server one (`policy-tools`) only

6 tools discovered:

- `check_policy_claim_history` (policy-tools)
- `compute_claim_payout` (policy-tools)
- `flag_for_review` (policy-tools)
- `get_claim` (policy-tools)
- `search_policy_text` (policy-tools)
- `submit_decision` (policy-tools)

## After — `mcp_config.json` with server one + server two (`claims-system`)

8 tools discovered:

- `check_policy_claim_history` (policy-tools)
- `compute_claim_payout` (policy-tools)
- `flag_for_review` (policy-tools)
- `get_adjuster_note_history` (claims-system)
- `get_claim` (policy-tools)
- `get_claim_status` (claims-system)
- `search_policy_text` (policy-tools)
- `submit_decision` (policy-tools)

**6 -> 8**, gained `get_claim_status` and `get_adjuster_note_history` from `claims-system`, purely from adding one entry to `mcp_config.json`. No file under `app/mcp_agent/` was touched — see `agent_diff.txt`.
