# Race table — single agent vs multi-agent orchestrator (Track D — Insurance Claims)

Same 10 claims (`analysis/week7/claims.json`, the fixed 10-claim
eval set carried over unchanged from the Week 6/7 evals — see requirement #1, do not
change the ruler), same programmatic judge (`expected_status`/`expected_payout` exact
match, `app/agent/tools.compute_payout`'s own arithmetic tolerance of $1).

**Latency note:** this race ran against the Gemini free tier's
`GenerateRequestsPerDayPerProjectPerModel-FreeTier` cap (20 requests/day, shared across
both arms and all API keys on this project). Several individual claim runs landed
exactly on that wall and sat in the client's hour-long retry-and-wait loop for hours
before a daily reset let them through — real wall-clock time, but not model or system
latency. p50/p99 below exclude any run whose elapsed time exceeds
500s (no clean run came within 5x of that threshold)
so the latency column reflects actual agent/orchestrator speed, not quota-queue time;
`polluted runs excluded` says how many were cut per arm. Pass rate, tokens and cost are
unaffected by this and use all 10 runs per arm.

| Arm | Pass rate | p50 latency (s) | p99 latency (s) | Total tokens | Cost/claim (USD) | Polluted runs excluded |
|---|---|---|---|---|---|---|
| single agent | 70% | 59.95 | 97.55 | 126629 | $0.000988 | 2/10 |
| multi-agent orchestrator | 80% | 48.78 | 89.72 | 69324 | $0.000583 | 2/10 |

## Context re-send multiplier: 0.5x

multi tokens (69324) / single tokens (126629) = 0.5x

Dominant hand-off: **manager -> exclusions worker**, 40534 tokens, 58% of all multi-agent tokens across the 10 claims (see `handoffs.log`).
