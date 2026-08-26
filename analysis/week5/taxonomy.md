# Week 5 — Failure Taxonomy (Track D — Insurance Claims)

Derived from open-coding a seeded random sample of 20 traces (seed 42, population
29) drawn from a real, Gemini-backed run of the app. See `notes.md` for the 20
verbatim observation sentences this table was clustered from.

| Mode                                                                                                                                                         | Count | Frequency % | Severity                                                                                        | Example trace_id |
|--------------------------------------------------------------------------------------------------------------------------------------------------------------|------:|------------:|-------------------------------------------------------------------------------------------------|------------------|
| A — Generation silently falls back to an unlabeled raw chunk dump on a transient provider error; the fact asked for is present but buried in noise           |     8 |         40% | Merely annoys the adjuster — the fact is recoverable with effort                                | `149efaef7f03`   |
| B — Same silent fallback, but the fact needed for part of the question is completely absent from the dump                                                    |     2 |         10% | Wrongly informs — reader has no way to find the missing fact from what's shown                  | `4ed2138134bb`   |
| C — Retrieval misses a chunk that verbatim answers the question, producing a false "I don't know" refusal                                                    |     1 |          5% | Wrongly denies available information to the customer                                            | `32ef08e43ed2`   |
| D — Two source documents disagree on the same coverage fact and the model doesn't flag the conflict; the answer to an identical question changes across runs |     1 |          5% | Wrongly denies or wrongly assures coverage depending on the run (confirmed unstable via replay) | `41744e44481e`   |

Remaining 8/20 (40%) were correctly handled — 6 accurate cited generations plus 2
correct refusals — with nothing to flag.

Severity legend: **wrongly denies/pays a claim** (high) vs **merely annoys the
adjuster** (low).
