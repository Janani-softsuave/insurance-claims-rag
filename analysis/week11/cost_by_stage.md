# Cost per query by stage — ClaimsWorkflow

## The found request (CLM-2027-00206, trace `feb7a7f0a446`)

| Stage | Latency | Tokens | Cost (USD) |
|---|---|---|---|
| retrieval (`search_policy`) | 2,715.95 ms | 0 | $0.000000 |
| generation (`workflow_decision`, 1 structured LLM call) | 7,604.65 ms | 1,826 | $0.00015967 |
| tools (`compute_payout`) | 543.19 ms | 0 | $0.000000 |
| **total** | **10,863.78 ms** | **1,826** | **$0.00015967** |

**Generation is 100% of this request's dollar cost.** Retrieval and tools run entirely
locally (embedding model + cross-encoder reranker + plain arithmetic) — Gemini is billed
only for the one structured-decision call.

## Average across all 12 real (non-synthetic) requests in `traces.jsonl`

| Stage | Avg latency | Avg tokens | Share of cost |
|---|---|---|---|
| retrieval | 5,122.8 ms | 0 | 0% |
| generation | 9,125.6 ms | 1,680.9 | 100% |
| tools | 582.8 ms | 0 | 0% |
| **total avg cost/query** | | | **$0.000143** |

## Two honesty caveats on these latency numbers

1. The 10 backfilled historical entries predate this week's per-span instrumentation — Week 7
   recorded one total `elapsed_seconds` per claim, not a per-stage split. Their retrieval/
   generation/tools latency above is a **25% / 70% / 5% proportional estimate** of that total,
   not independently measured. Only the two live entries from this week's RED/GREEN
   confirmation (`35cd01674f12`, `190d27d5ddde`) have genuinely per-span-measured latency.
2. Those two live entries' retrieval latency (12.9s and 13.6s) is inflated by **cold-start
   model loading** — `BAAI/bge-small-en-v1.5` and the reranker get loaded fresh in every
   one-off script invocation in this dev environment. In a running service that keeps those
   models resident in memory, retrieval latency per request would be the embedding + rerank
   compute only — on the order of tens to a few hundred milliseconds, not seconds. Cost by
   stage (the dollar figure, which is what actually accumulates at volume) is unaffected by
   this — retrieval and tools are $0 either way.

**Bottom line on cost:** this workflow's entire per-query bill is one Gemini call, ~1,700-1,900
tokens, **≈$0.00015/query**. There is no retrieval or tools cost to optimize — the only lever
for cost is the generation call itself (fewer tokens, cheaper model, or caching repeat
questions).
