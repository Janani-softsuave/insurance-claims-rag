# Bonus — one gateway, one audit log, one scoped token denial

`app/mcp_servers/gateway_server.py` fronts both `policy-tools` and `claims-system` behind a
single MCP server. The agent's `mcp_config.json` now names one server (`claims-gateway`); the
gateway opens its own stdio connections to both backends at startup (its `lifespan`), merges
their 8 tools into one `tools/list`, and proxies every `tools/call` to whichever backend
actually owns that tool name.

## One audit line per `tools/call`

Every call - allowed or denied - writes exactly one line to `analysis/week9/audit.log`:
`timestamp | caller=<token scope> | tool=<name> | claim_number=<if present> | allowed=<bool>`.
Real log from two back-to-back runs on the same claim, two different tokens:

```
2026-09-22T11:09:47 | caller=full | tool=get_claim | claim_number=CLM-2027-00206 | allowed=True
2026-09-22T11:09:47 | caller=full | tool=get_claim_status | claim_number=CLM-2027-00206 | allowed=True
2026-09-22T11:09:49 | caller=full | tool=get_adjuster_note_history | claim_number=CLM-2027-00206 | allowed=True
2026-09-22T11:09:49 | caller=full | tool=search_policy_text | claim_number= | allowed=True
2026-09-22T11:10:12 | caller=full | tool=compute_claim_payout | claim_number= | allowed=True
2026-09-22T11:10:17 | caller=full | tool=submit_decision | claim_number=CLM-2027-00206 | allowed=True
2026-09-22T11:10:50 | caller=claims-status-only | tool=get_claim | claim_number=CLM-2027-00206 | allowed=True
2026-09-22T11:10:50 | caller=claims-status-only | tool=get_claim_status | claim_number=CLM-2027-00206 | allowed=True
2026-09-22T11:10:53 | caller=claims-status-only | tool=get_adjuster_note_history | claim_number=CLM-2027-00206 | allowed=False
2026-09-22T11:10:53 | caller=claims-status-only | tool=search_policy_text | claim_number= | allowed=True
2026-09-22T11:11:09 | caller=claims-status-only | tool=compute_claim_payout | claim_number= | allowed=True
2026-09-22T11:11:13 | caller=claims-status-only | tool=submit_decision | claim_number=CLM-2027-00206 | allowed=True
```

(`claim_number` is blank for tools that don't take one, e.g. `search_policy_text`'s argument
is `query` - the audit line still fires, just with nothing to show there.)

## Scoped token: `claims-status-only` denies adjuster notes, claim status still works

The token is passed as an env var (`GATEWAY_TOKEN`) when the gateway subprocess is spawned -
the closest local analog to a bearer token on a stdio transport with no HTTP headers to carry
one. `mcp_config.json` (full access) vs `mcp_config.limited.json` (scoped) differ only in that
one env value.

Same claim (`CLM-2027-00206`), same agent code, only the token config differs:

**Full token** - `get_adjuster_note_history` succeeds, full transcript reaches `submit_decision`
with `status=denied, payout=0`.

**Scoped token (`claims-status-only`)** - real transcript:

```
iter 1: get_claim(...) -> {claim record}
iter 1: get_claim_status(...) -> {"claim_number": "CLM-2027-00206", "status": "denied"}
iter 2: get_adjuster_note_history(...) -> {"error": "tool 'get_adjuster_note_history' denied
  for token scope 'claims-status-only': this token is limited to claim-status lookups,
  adjuster notes require a different token."}
iter 2: search_policy_text({'query': 'burglary theft forced and violent entry unlocked back
  door'}) -> {policy passages}
iter 3: compute_claim_payout(claim_status=denied, ...) -> {"payout": 0.0}
iter 4: submit_decision(...) -> status=denied, payout=0.0
```

**The denial reached the model as a recoverable message, not a crash.** The gateway didn't
close the connection or raise a protocol-level error - it returned a normal tool result whose
content happens to be `{"error": "..."}`, exactly like any other tool error in this project.
The model read it, understood adjuster notes weren't available *this time*, and fell back to
`search_policy_text` (which the scoped token still permits) to find the same forcible-entry
requirement the adjuster notes would have confirmed - reaching the identical, correct `denied`
outcome either way. `claim_number` in the denial line makes it auditable *which* claim a
denied lookup was attempted against, not just that a denial happened.

## Design note

`get_claim_status` stayed permitted throughout - the scope denies exactly one tool
(`get_adjuster_note_history`), matching the bonus's ask precisely: "the adjuster-note tool is
denied while claim status still works."
