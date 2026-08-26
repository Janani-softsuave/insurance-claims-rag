# Week 5 — Error Analysis Notes (Track D — Insurance Claims)

Produced by running the app for real (Gemini `gemini-2.5-flash`, ingested from
`data/raw/`) via `scripts/collect_week5_traces.py` plus manually-run questions,
then `app.cli trace sample` and `app.cli trace replay`. Zero code changes were
made while open-coding section 4.

**Update:** after the first pass, 10 more real traces were added to the trace log
(a new source document was ingested — `20240928002-group-home-protect-policy-...pdf`
— plus several manually-asked questions). The population grew from 29 to 39, so
the seeded sample was **redrawn** against the new population. Sections 2 and 4
below reflect the recalculated sample; nothing in the earlier pass was reused
except the replay evidence in section 3, whose subject trace is still present in
the log and unaffected by the new traces.

## 1. Redaction confirmation

Confirmed: `RagService._write_trace` (`app/services/rag_service.py`) calls
`app.core.tracing.redact()` on the question and the answer and builds the `Trace`
object from the *redacted* strings — the original text is never passed to
`write_trace()`. Verified on trace `0b8f69079533` (one of the newly-added traces),
whose question was `"My name is Rohan Mehta and my claim number is
CLM-2024-00931 — why was it rejected?"`; the persisted `question_redacted` field
reads: `"My name is [REDACTED_NAME] and my claim number is [REDACTED_CLAIM_NO] —
why was it rejected?"`.

## 2. Seeded random sample

- Seed: **42**
- Population size (total traces logged): **39**
- Sample size: **20**
- Trace IDs (from `analysis/week5/sample_trace_ids.json`):
  `45dafbfb8ebd, f8b0b1bd74c6, 10f7e5c0cc6e, 32ef08e43ed2, 62a7fdf66478,
  c6ba55cfed03, 9a7d425b0f18, 21101750e4b7, 0b8f69079533, 4ed2138134bb,
  4fba407a82e7, a22cea304a71, 873d5923d5e4, 2069d746c243, ddfd604935ff,
  8d5ddacf164d, ad9507f705f3, 86ebf155edf6, fce2e2caebd6, 4f9b8701f5ba`

## 3. Replay evidence

- trace_id: `41744e44481e`
- Question: "Is my home covered for earthquake damage?"
- prompt_version: `v2-fewshot` · model: `gemini-2.5-flash`
- Fields the trace already carried: redacted question, retrieval_mode, 4 retrieved
  `chunk_id`s + scores, prompt_version, model, generation_params, can_answer,
  citations, latency_ms.
- Fields that had to be added: none — `app.cli trace replay` refetched all 4 chunks
  by id from the live ChromaDB collection (`get_by_ids`) with zero misses, and
  re-ran generation with the exact same model and prompt version stored on the
  trace.
- What could not be reconstructed: the original, un-redacted question text — by
  design (see `REDACTION_LIMITATIONS` in `app/core/tracing.py`). This particular
  question had no PII, so it didn't matter here, but it is a structural limitation:
  replay always runs on the redacted text.
- ORIGINAL answer:
  ```
  Standard fire policies do not cover earthquake damage by default. To be covered,
  you need the Earthquake Extension endorsement (IAP-01). If this endorsement is
  in place, both fire following an earthquake and shock damage are covered.
  ```
- REPLAYED answer:
  ```
  Standard fire policies do not cover earthquake damage by default; the Earthquake
  Extension endorsement (IAP-01) is required for coverage of fire following
  earthquake and shock damage. However, 'Building Cover' policies, as described in
  Section 3.1, do include earthquake coverage for the structure.
  ```
  The replay used the identical question, chunks, model, and prompt — and still
  produced a materially different answer (the replay adds a sentence that
  contradicts the original). This trace was not part of the recalculated 20-sample,
  but it remains in the trace log unchanged, and the underlying source-document
  contradiction it exposes (see mode D, noted below the taxonomy table) has not
  been touched.

## 4. Open coding — 20 verbatim sentences (one per sampled trace)

Rules followed: one honest sentence per trace describing what was SEEN, not a
category or a fix. Zero code changes were made while writing this section. Twelve
of these traces were also in the first-pass sample and keep their original
sentence unchanged; eight are new to the sample.

1. `45dafbfb8ebd` — The answer correctly said IDV for vehicles over 5 years is mutually agreed upon, matching the FAQ, with a supporting citation.
2. `f8b0b1bd74c6` — The answer correctly explained that flood damage is covered under comprehensive cover but engine hydrostatic lock needs the IMT-29 endorsement, matching the FAQ precisely.
3. `10f7e5c0cc6e` — The answer was a raw chunk dump; the ₹25,000 burglary cash limit is present in the second paragraph, but it's surrounded by an unrelated deductibles table and an IMT-28 tyre-depreciation FAQ entry.
4. `32ef08e43ed2` — The answer said "I don't know," but the FAQ document contains an exact, on-topic answer ("Minor renovation ... does not affect coverage") that simply wasn't among the four chunks retrieved for this question.
5. `62a7fdf66478` — The answer was a raw chunk dump that names "policy lapse" as a rejection reason but never states the 15-day grace period number itself; two of its four retrieved chunks were an unrelated health-policy refund-on-cancellation clause instead of the policy overview's actual grace-period section.
6. `c6ba55cfed03` — The answer correctly refused, saying the documents don't mention jewellery coverage under a motor policy, which matches what the four retrieved chunks actually contain.
7. `9a7d425b0f18` — The answer correctly said the ₹1,000 deductible is waived for a windshield-only glass-breakage claim, matching the FAQ.
8. `21101750e4b7` — The answer correctly cited the IAP-12 endorsement's ₹25,000-per-month rent for up to 6 months, matching the endorsements document.
9. `0b8f69079533` — The answer correctly refused, saying it couldn't find an answer, after the question's claimant name and claim number were redacted to `[REDACTED_NAME]` and `[REDACTED_CLAIM_NO]` before generation was even attempted.
10. `4ed2138134bb` — The answer was a raw chunk dump describing what third-party liability covers, but none of the four chunks ever explicitly states that TPL excludes the policyholder's own vehicle — that has to be inferred by the reader from the absence of any such statement.
11. `4fba407a82e7` — The answer was a raw chunk dump from the newly-added group-home-protect PDF; the exact matching exclusion ("loss of any insured item which is missing or mislaid ... cannot be linked to any single identifiable event") is present as item 7 in a numbered exclusions list, but it's surrounded by unrelated exclusions (bullion, market-value reduction, consequential loss) with no direct yes/no answer synthesized.
12. `a22cea304a71` — The answer correctly and concisely stated the 24-hour theft-reporting window with a matching citation, with nothing to flag.
13. `873d5923d5e4` — The answer correctly said tyres still carry 50% depreciation despite Zero Dep cover, matching the FAQ's explicit exception.
14. `2069d746c243` — The answer correctly said it doesn't know, but all four retrieved chunks came from the new group-home-protect PDF at scores barely above the 0.5 floor, and the existing claims_faq.md passage about escalating to the Insurance Ombudsman "in your city" wasn't retrieved at all even though it's the closest thing to relevant in the whole corpus.
15. `ddfd604935ff` — This is a repeat of the exact same question as trace `4fba407a82e7` — same four retrieved chunks, same raw chunk dump — and it hit the identical quota-exhaustion fallback both times, showing the failure isn't a one-off blip but repeats deterministically for this question while the quota is out.
16. `8d5ddacf164d` — The answer was a raw chunk dump that answers the mechanical-breakdown half of the question (excluded unless accident-related), but none of the four retrieved chunks contain the "endorsements can be added mid-term" section, so the first half of the question is left completely unaddressed.
17. `ad9507f705f3` — The answer correctly refused an out-of-domain question, and all four retrieved chunks scored exactly at the 0.5 grounding floor, confirming retrieval genuinely found nothing relevant.
18. `86ebf155edf6` — The answer was a raw chunk dump that does contain the "spot survey via video call for claims below ₹50,000" fact, but it's positioned mid-paragraph inside claim-settlement text with no direct yes/no answer to the question asked.
19. `fce2e2caebd6` — The answer correctly said flood damage to the house structure is covered, drawing on the Building Cover section, though one of its four retrieved chunks was the motor-claims flood FAQ entry (about car engines) rather than property-specific content.
20. `4f9b8701f5ba` — The answer was a raw chunk dump containing both the IDV and RTI definitions verbatim, but never assembled them into the side-by-side comparison the question actually asked for.

## 5. Dated, falsifiable prediction

- Date: **2026-08-26** (recalculated from the first-pass prediction, same date)
- Mode being attacked next: **Mode A — silent fallback to an unlabeled raw chunk
  dump on a transient provider error; the fact asked for is present but buried in
  noise** (see `taxonomy.md`). Still the largest mode after recalculation (25%,
  down from 40% in the first-pass sample, but still the single biggest bucket).
- Specific change: add up to 2 retries with exponential backoff (2s, then 5s)
  inside `Generator.generate()` before `RagService.ask()` gives up and falls back
  to `_retrieval_only_response()`.
- Expected delta: on a fresh 20-trace random sample collected the same way, Mode A
  drops from **25% (5/20) to under 10% (2/20)**.
- Git commit hash: `e6ba521`

## 6. Why a public benchmark would have missed the top-3 modes

MMLU/HumanEval-style benchmarks score a fixed model checkpoint's answers to public,
pre-written questions under ideal conditions, so they would never surface Mode A at
all — it's caused by our own provider quota and transient errors, not by anything
the model got wrong. Modes B, C and E depend entirely on this company's private
policy documents having specific retrieval gaps — a missing renovation clause, a
grace-period number that isn't in the top-4 chunks, or a brand-new PDF that
out-competes an older, more relevant file in the same corpus — and no public
benchmark has ever seen these documents, so it has no way to know any of that.
And benchmarks report one accuracy number from one run, while mode D (see below the
taxonomy table) is fundamentally about the *same* question producing *different*
answers across runs — a property a single-shot benchmark score isn't designed to
measure at all.

## Bonus challenge

Not attempted — no curated "monthly review" demo set exists for this project yet;
all 39 traces come from the same randomly-generated (plus a few manually-asked)
question set.
