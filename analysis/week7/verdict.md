# Week 7 Verdict — Agent vs Workflow (Track D — Insurance Claims)

Across the same 10 claims, the workflow is faster (p50 10.6s vs 39.6s),
cheaper (16.6k vs 109.5k total tokens, ~6x), and simpler — but the agent
scores higher on correctness (80% vs 70%). The three claims the workflow got
wrong share one trait: the correct answer required a second look — either
applying an exception nested inside an already-matched coverage rule
(CLM-2027-00205's Zero Dep tyre still carrying standard depreciation) or
reconciling an exclusion phrased differently from the adjuster's notes
(CLM-2027-00206's "left unlocked" vs the policy's "unforced entry"). The
workflow's single fixed call answered once and moved on; the agent visibly
re-searched and self-corrected on both. That's the claim class that needs an
agent: coverage decisions requiring a second, exception-checking pass. But the
agent also failed two claims outright by timing out mid-search — not a case
for it running unsupervised yet.

(141 words)
