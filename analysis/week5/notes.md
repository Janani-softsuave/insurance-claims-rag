# Week 5 — Error Analysis Notes (Track D — Insurance Claims)

Produced by running the app for real (Gemini `gemini-2.5-flash`, 296 chunks ingested
from `data/raw/`) via `scripts/collect_week5_traces.py`, then `app.cli trace sample`
and `app.cli trace replay`. Zero code changes were made while open-coding section 4.

## 1. Redaction confirmation

Confirmed: `RagService._write_trace` (`app/services/rag_service.py`) calls
`app.core.tracing.redact()` on the question and the answer and builds the `Trace`
object from the *redacted* strings — the original text is never passed to
`write_trace()`. Verified on trace `0b8f69079533`, whose question was
`"My name is Rohan Mehta and my claim number is CLM-2024-00931 — why was it
rejected?"`; the persisted `question_redacted` field reads:
`"My name is [REDACTED_NAME] and my claim number is [REDACTED_CLAIM_NO] — why was
it rejected?"`.

## 2. Seeded random sample

- Seed: **42**
- Population size (total traces logged): **29**
- Sample size: **20**
- Trace IDs (from `analysis/week5/sample_trace_ids.json`):
  `149efaef7f03, 41744e44481e, a22cea304a71, 11c87ea02445, c6ba55cfed03,
  45dafbfb8ebd, 4f9b8701f5ba, 0eefb31df041, 86ebf155edf6, 10f7e5c0cc6e,
  873d5923d5e4, 4ed2138134bb, f8b0b1bd74c6, 119a3c3662fa, 8d5ddacf164d,
  6427c16ba118, ad9507f705f3, e24308e06772, a7dcd766ef72, 32ef08e43ed2`

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
  contradicts the original). This is itself evidence for failure mode D below.

## 4. Open coding — 20 verbatim sentences (one per sampled trace)

Rules followed: one honest sentence per trace describing what was SEEN, not a
category or a fix. Zero code changes were made while writing this section.

1. `149efaef7f03` — The answer was a raw concatenation of four retrieved chunks — including two unrelated snippets about overseas medical treatment from the health policy PDF — with no synthesized comparison sentence, even though a clean cashless-vs-reimbursement table was buried inside the dump.
2. `41744e44481e` — The answer said earthquake damage is not covered without the IAP-01 endorsement, but one of its own four retrieved chunks (the Building Cover section) lists earthquake among the perils a standard building policy covers, and the answer never acknowledged that the two sources disagree.
3. `a22cea304a71` — The answer correctly and concisely stated the 24-hour theft-reporting window with a matching citation, with nothing to flag.
4. `11c87ea02445` — The answer was an unsynthesized chunk dump that mixed the correct 5% long-term motor discount with an unrelated health-policy discount table (7.5%/10% for 2- and 3-year health plans), so two different discount numbers for two different products sit side by side with nothing distinguishing them.
5. `c6ba55cfed03` — The answer correctly refused, saying the documents don't mention jewellery coverage under a motor policy, which matches what the four retrieved chunks actually contain.
6. `45dafbfb8ebd` — The answer correctly said IDV for vehicles over 5 years is mutually agreed upon, matching the FAQ, with a supporting citation.
7. `4f9b8701f5ba` — The answer was a raw chunk dump containing both the IDV and RTI definitions verbatim, but never assembled them into the side-by-side comparison the question actually asked for.
8. `0eefb31df041` — The answer correctly distinguished that the building policy covers only the structure and that landlord liability to the tenant depends on the Landlord's Legal Liability endorsement, matching the FAQ.
9. `86ebf155edf6` — The answer was a raw chunk dump that does contain the "spot survey via video call for claims below ₹50,000" fact, but it's positioned mid-paragraph inside claim-settlement text with no direct yes/no answer to the question asked.
10. `10f7e5c0cc6e` — The answer was a raw chunk dump; the ₹25,000 burglary cash limit is present in the second paragraph, but it's surrounded by an unrelated deductibles table and an IMT-28 tyre-depreciation FAQ entry.
11. `873d5923d5e4` — The answer correctly said tyres still carry 50% depreciation despite Zero Dep cover, matching the FAQ's explicit exception.
12. `4ed2138134bb` — The answer was a raw chunk dump describing what third-party liability covers, but none of the four chunks ever explicitly states that TPL excludes the policyholder's own vehicle — that has to be inferred by the reader from the absence of any such statement.
13. `f8b0b1bd74c6` — The answer correctly explained that flood damage is covered under comprehensive cover but engine hydrostatic lock needs the IMT-29 endorsement, matching the FAQ precisely.
14. `119a3c3662fa` — The answer was a raw chunk dump; both the "4 events per policy year" limit and "battery jump-start" as a covered service are present verbatim, but never combined into a direct answer to the two-part question.
15. `8d5ddacf164d` — The answer was a raw chunk dump that answers the mechanical-breakdown half of the question (excluded unless accident-related), but none of the four retrieved chunks contain the "endorsements can be added mid-term" section, so the first half of the question is left completely unaddressed.
16. `6427c16ba118` — The answer was a raw chunk dump; the exact sentence "Not covered: normal wear and tear, mechanical or electrical breakdown" is present verbatim in the first chunk, but it's never surfaced as a direct answer.
17. `ad9507f705f3` — The answer correctly refused an out-of-domain question, and all four retrieved chunks scored exactly at the 0.5 grounding floor, confirming retrieval genuinely found nothing relevant.
18. `e24308e06772` — The answer was a raw chunk dump; the specific clause that "driving into a flooded area knowingly may lead to repudiation" is present inside the IMT-29 paragraph, but it's buried past unrelated RTI and claim-rejection text with no direct answer to the deliberate-driving scenario asked.
19. `a7dcd766ef72` — The answer correctly walked through the full four-step grievance escalation path (rejection letter, Grievance Cell, Ombudsman, IRDAI IGMS portal), matching the FAQ exactly.
20. `32ef08e43ed2` — The answer said "I don't know," but the FAQ document contains an exact, on-topic answer ("Minor renovation ... does not affect coverage") that simply wasn't among the four chunks retrieved for this question.

## 5. Dated, falsifiable prediction

- Date: **2026-08-26**
- Mode being attacked next: **Mode A — silent fallback to an unlabeled raw chunk
  dump on a transient generation error** (see `taxonomy.md`).
- Specific change: add up to 2 retries with exponential backoff (2s, then 5s)
  inside `Generator.generate()` before `RagService.ask()` gives up and falls back
  to `_retrieval_only_response()`.
- Expected delta: on a fresh 20-trace random sample collected the same way, Mode A
  drops from **40% (8/20) to under 15% (3/20)**.
- Git commit hash: `b4a1faa`

## 6. Why a public benchmark would have missed the top-3 modes

MMLU/HumanEval-style benchmarks score a fixed model checkpoint's answers to public,
pre-written questions under ideal conditions, so they would never surface Mode A at
all — it's caused by our own provider quota and transient 503 errors, not by
anything the model got wrong. Modes C and D depend entirely on this company's
private policy documents having a specific retrieval-index gap and a specific
internal contradiction between two of our own PDFs, and no public benchmark has
ever seen these documents, so it has no way to know a renovation-related sentence
sits outside the top-4 retrieved chunks or that two of our own sections disagree
about earthquake coverage. And benchmarks report one accuracy number from one run,
while Mode D is fundamentally about the *same* question producing *different*
answers across runs — a property a single-shot benchmark score isn't designed to
measure at all.

## Bonus challenge

Not attempted — no curated "monthly review" demo set exists for this project yet;
all 29 traces come from the same randomly-generated question set.
