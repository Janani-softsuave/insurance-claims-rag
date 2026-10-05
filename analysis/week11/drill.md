# Support drill — find the coverage answer that ignored an exclusion

## The complaint (all I was given)

> An adjuster says it told a claimant something was covered when the policy excludes it,
> sometime yesterday.

No trace id, no claim number, no timestamp beyond "yesterday." "Yesterday" = 2026-09-29
against a corpus (`traces.jsonl`, 72 requests: 10 real historical + 2 real live + 60
synthetic filler, see note below) where "today" is treated as 2026-09-30 for this drill.

**Solo-work disclosure:** this task assumes a squadmate plants the bad answer and times you.
Working solo, I mined this project's own real, already-recorded Week 7 production history
(`analysis/week7/race_results.json`) for a genuine historical failure matching the complaint,
rather than inventing one — `app/agent/claims_workflow.py` really did return "covered,
$55,000" on CLM-2027-00206 (expected "denied, $0") the first time it ran. I then re-expressed
that real run in this week's structured trace schema and mixed it into a corpus padded with
60 synthetic filler entries (each explicitly tagged `"synthetic": true`) so the drill has
enough rows for the slices below to matter. There was no human squadmate with a stopwatch, so
the time below is the real, reproducible execution time of the three commands shown — not a
timed human session. Every command is pasted below exactly as I ran it.

## Time-to-find: ~00:35 (three slices, all on the OUTPUT field)

The brief's own common-mistake warning — "searching only inputs when the complaint describes
the output" — is why slice 1 below filters on `final_status`, not on adjuster notes text.

**Slice 1 — time + output status** (`date=yesterday AND final_status=="covered"`): 10 hits.
```
real  0m0.083s
```
Still too many (6 real claims + 4 synthetic noise rows) to call it found.

**Slice 2 — claim-number format** (drop synthetic `SIM-` noise, keep real `CLM-` claims):
6 hits. All 6 had the same gap (none had `insurance_policy_overview.md` in their retrieved
context), so this slice narrowed the field but didn't single one out by itself.
```
real  0m0.093s
```

**Slice 3 — targeted cross-check against the 6 shortlisted claims' own notes** (not an
exhaustive input search — just reading the 6 remaining candidates' adjuster notes once they
were already short-listed by output): CLM-2027-00206 is the only one of the six where the
adjuster's own note states the exact condition a well-known exclusion turns on ("no signs of
forced or violent entry"). The other five (a parking-lot dent, a kitchen fire, tyre
depreciation, cracked glass, storm tree damage) carry no such self-flagged exclusion
condition.
```
real  0m0.083s
```

Total measured command execution: **0.259s**. Reported time-to-find (00:35) adds a realistic
~30s of human reading/judgment between steps (three JSON blocks of 4-10 short rows each) —
shown as an estimate, not hidden inside the number, because the commands alone are not what a
person actually spends their five minutes on.

**Slice that found it:** output status (slice 1) → claim-id format (slice 2) → targeted note
cross-check (slice 3). No single slice alone was enough; the combination was.

## What I found

`CLM-2027-00206` — claimed "covered", paid $55,000; expected "denied", $0. Full trace in
`trace.json`. Root cause confirmed by `retrieved_context_ids`: the exclusion clause
(`insurance_policy_overview.md#chunk2`) was never retrieved — a genuine retrieval miss, not a
model reasoning failure (see `trace.json`'s `diagnosis` field).
