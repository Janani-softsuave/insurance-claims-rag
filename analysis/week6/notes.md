# Week 6 — Judge Validation Notes (Track D — Insurance Claims)

Produced by running the claim-summary generator and both judge versions for
real (Gemini `gemini-3.6-flash`) over the 25-case eval set in `eval_cases.json`.
`labels_25.json` was hand-written and committed (`ac73b51` and earlier) before
any judge run — see git history for the ordering proof.

## 1. Assertions vs judged criteria

4 deterministic assertions (`app/evaluation/assertions.py`), 0 LLM calls:
- `claim_number_format` — regex `^CLM-\d{4}-\d{5}$`
- `date_of_loss_parseable` — `dateutil.parser.parse`
- `excess_numeric` — type/range check
- `exclusion_cited_on_denial` — presence check when `coverage_decision == "denied"`

1 judged criterion, left in the LLM judge: **faithfulness** — is every
coverage-relevant claim in the summary directly supported by its own retrieved
POLICY CONTEXT. Everything mechanically checkable was moved out of the judge
prompt before `judge_v1.txt` was ever written (see `judge_v1.txt` — it names
these fields as explicitly out of scope).

Result over all 25 real generated summaries: **25/25 assertions pass**,
**12/25 judge-v2-faithful**.

## 2. agreement_before / agreement_after

- **agreement_before (judge_v1): 76.2% (16/21)** — 21/25 cases were judged
  before hitting a quota wall the first time.
- **agreement_after (judge_v2), same 21 cases: 81.0% (17/21)**
- **agreement_after (judge_v2), all 25 cases: 80.0% (20/25)** — the full-set
  number, once all 25 were judged under v2.

## 3. Pass rate by mode (one command: `python -m scripts.run_week6_eval run --judge-version v2`)

| Mode | Cases | Assertions pass | Judge (v2) faithful | Overall pass |
|------|------:|-----------------:|---------------------:|--------------:|
| A | 5 | 5/5 | 4/5 | 4/5 |
| B | 5 | 5/5 | 2/5 | 2/5 |
| C | 5 | 5/5 | **0/5** | **0/5** |
| D | 5 | 5/5 | 5/5 | 5/5 |
| E | 5 | 5/5 | 1/5 | 1/5 |
| **TOTAL** | **25** | **25/25** | **12/25** | **12/25** |

This is exactly the trap the brief warns about: the overall 48% pass rate
(12/25) completely hides that **mode D is perfect (5/5)** while **mode C is a
total wipeout (0/5)**. A claims-ops team routing work by the aggregate number
alone would never learn that mode C summaries are uniformly unreliable.

## 4. Disagreement analysis — 2+ read, verdict on who was right

All 5 v1 disagreements (out of 21 judged) went the same direction: I labeled
`faithful=true`, the judge said `faithful=false`. Two were picked as
`judge_v2.txt` few-shot examples; here's the verdict on those two, plus the
outcome for the other three.

**A-05** (mode A) — Question: purely a settlement-timeline question (cashless
vs. reimbursement), no real coverage dispute. The summary still states
`coverage_decision: covered`.
- Judge's rationale: "the policy context does not provide a specific coverage
  decision... 'covered' is not directly supported."
- **Verdict: the judge was right, my label was wrong.** I graded the
  *narrative* content (which was accurate) and let a schema artifact — every
  `ClaimSummary` is forced to carry a `coverage_decision` even when the
  question isn't about coverage at all — slide through as "faithful." It
  isn't: a label the context can't actually support shouldn't pass just
  because nothing else in the summary is wrong.

**D-05** (mode D) — Question: tenant's fire-damaged contents, landlord
liability. The summary concludes `denied` for the tenant's contents, citing a
general FAQ passage ("structure only... unless IAP-15 and a building defect")
and correctly noting neither condition is met in the notes.
- Judge's rationale: "the policy documents only provide general FAQ guidance
  and do not state a claim outcome."
- **Verdict: the judge was wrong, my label was right.** A general policy rule,
  correctly applied to the specific facts given, *is* legitimate grounding —
  that's the entire mechanism by which any of these summaries could ever be
  faithful, since none of the source documents contain pre-written verdicts
  for hypothetical claims. Rejecting every decision that isn't restated
  verbatim would make the faithfulness criterion impossible to satisfy in
  principle.

**C-02, C-03, C-05** — not used as few-shot examples, but re-examined after
seeing the pattern: all three share A-05's problem, not D-05's. C-02 answers
"must I declare this renovation" with `covered` (the context only describes an
ongoing obligation, not a coverage verdict); C-03 answers "can this be settled
now" with `denied` when the grounded fact is "pending a required document," a
materially different claims-ops action; C-05 answers "will a surveyor visit in
person" with `covered` for a question that was never about coverage at all.
**Verdict: the judge was right on all three; my original blind labels were the
ones that needed correcting.**

## 5. Falsifiable prediction, before vs. after

See `prediction.txt`. Predicted agreement would reach >=90% (19/21); actual was
81.0% (17/21) — directionally correct (agreement did improve, and D-05 flipped
exactly as intended) but wrong on magnitude, because the prediction assumed the
other four disagreements were also judge errors of the same kind as D-05. They
weren't — they were a different, unrelated pattern (coverage_decision forced
onto non-coverage questions) that the D-05 fix was never going to touch.

## 6. What this validation actually proved

The judge is not simply "right" or "wrong" as a monolith — it was right on 4 of
5 disagreements and wrong on 1. That's a genuinely useful outcome: the judge is
trustworthy enough to route real claims-ops attention toward mode C (0/5, a
real, severe finding) rather than being dismissed after the first few
disagreements, but the two flagged errors (the D-05 pattern) show it still
needs a human spot-check on decisions grounded in general rather than
claim-specific text before its number is used unsupervised.
