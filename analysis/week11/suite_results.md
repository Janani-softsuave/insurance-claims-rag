# Suite results — RED before the fix, GREEN after

Same 10 claims (`analysis/week7/claims.json`), same programmatic judge
(`expected_status`/`expected_payout` exact match), same component (`ClaimsWorkflow`).

## RED — `prompt_version=v1` (the real historical Week 7 production run; re-confirmed live
today on the planted case, see `trace.json` / `drill.md`)

**7/10 pass.** Three failures: `CLM-2027-00206` (this week's planted failure — "covered,
$55,000" when the policy excludes it), `CLM-2027-00205` (depreciation-exception bug, a
different and already-known issue), `CLM-2027-00209` (DUI-exclusion bug, also different and
already-known).

## GREEN — `prompt_version=v2-retrieval-widened` (full suite re-run after the fix, today)

**8/10 pass.**

| Claim | Status | Result |
|---|---|---|
| CLM-2027-00201 | denied / $0 | PASS |
| CLM-2027-00202 | covered / $17,000 | PASS |
| CLM-2027-00203 | denied / $0 | PASS |
| CLM-2027-00204 | covered / $80,000 | PASS |
| CLM-2027-00205 | covered / $11,000 (expected partial / $5,500) | **FAIL — unchanged, different bug** |
| **CLM-2027-00206** | **denied / $0** | **PASS — the planted failure, fixed** |
| CLM-2027-00207 | covered / $4,500 | PASS |
| CLM-2027-00208 | pending / $0 | PASS |
| CLM-2027-00209 | pending / $0 (expected denied / $0) | **FAIL — unchanged, different bug** |
| CLM-2027-00210 | covered / $140,000 | PASS |

## What moved and what didn't

**7/10 -> 8/10.** Exactly the one targeted claim flipped (206: FAIL -> PASS), and the six
claims that already passed still pass — the retrieval-layer fix (widening `search_policy`'s
dense candidate pool) did not silently break anything else, which is the whole point of
re-running the full suite instead of just the one case. 205 and 209 are real, pre-existing,
different-root-cause failures (a depreciation/status-field mismatch and a DUI-exclusion miss,
neither a retrieval problem) that this fix was never meant to touch and honestly didn't.
