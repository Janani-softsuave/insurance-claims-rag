# Week 5 — Failure Taxonomy (Track D — Insurance Claims)

Derived from open-coding a seeded random sample of 20 traces (seed 42, population
**39**, recalculated after 10 new traces were added — see `notes.md`). See
`notes.md` for the 20 verbatim observation sentences this table was clustered from.

| Mode | Count | Frequency % | Severity | Example trace_id |
|------|------:|------------:|----------|-------------------|
| A — Generation silently falls back to an unlabeled raw chunk dump on a transient provider error; the fact asked for is present but buried in noise | 5 | 25% | Merely annoys the adjuster — the fact is recoverable with effort | `10f7e5c0cc6e` |
| B — Same silent fallback (or a real answer), but the specific fact needed is completely absent from the retrieved chunks | 3 | 15% | Wrongly informs — reader has no way to find the missing fact from what's shown | `62a7fdf66478` |
| C — Retrieval misses a chunk that verbatim answers the question, producing a false "I don't know" refusal | 1 | 5% | Wrongly denies available information to the customer | `32ef08e43ed2` |
| E — Retrieval anchors on a newly-ingested, larger document and misses a relevant (if imperfect) passage that already exists in a different, older file | 1 | 5% | Merely annoys the adjuster — the answer is a reasonable refusal, but for the wrong reason | `2069d746c243` |

Remaining 10/20 (50%) were correctly handled — 8 accurate cited generations plus
2 correct refusals — with nothing to flag.

**Not in this sample, but real and still present in the corpus:** mode D — two
source documents (`claims_faq.md` and `insurance_policy_overview.md`) disagree
about whether earthquake damage is covered, and the model doesn't flag the
conflict; the answer to the identical question changes across runs. This mode had
0 occurrences in the current 20-trace sample purely by sampling variance, but it
is directly demonstrated by the replay evidence in `notes.md` §3 (trace
`41744e44481e`), so it is not reported here with a fabricated frequency — it is
flagged as a known, reproducible, high-severity issue (wrongly denies or wrongly
assures earthquake coverage depending on the run) worth tracking in the next
sampling round.

Severity legend: **wrongly denies/pays a claim** (high) vs **merely annoys the
adjuster** (low).
