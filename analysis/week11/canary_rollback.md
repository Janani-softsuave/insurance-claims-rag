# Prompt/retrieval version bump: v1 -> v2-retrieval-widened

`app/agent/claims_workflow.py`'s `WORKFLOW_PROMPT_VERSION` moved from `"v1"` to
`"v2-retrieval-widened"`. No prompt text changed — the fix is in `app/agent/tools.py`'s
`search_policy`: dense-retrieval candidate pool widened from `top_k` (4) to `max(top_k*2, 8)`
before reranking narrows back down, so a relevant chunk ranked just outside the old cutoff
(like this claim's exclusion clause, which ranked #5 against a #4 cutoff) now survives to be
reranked instead of being discarded before reranking ever sees it.

**Canary:** ship `v2-retrieval-widened` to 10% of workflow traffic for 24h, watching the
regression suite's pass rate and the per-query token/cost delta (widening retrieval sends the
same final `top_n=4` chunks to the LLM, so cost should not move — promote to 100% only if both
hold).

**Rollback:** `search_policy`'s pool-widening is a one-line parameter (`dense_pool_size`);
reverting it to `top_k` restores exact `v1` retrieval behavior instantly, no redeploy of the
decision prompt or model needed, if the regression suite's pass rate drops or latency moves
outside 2x of today's `v1` baseline.
