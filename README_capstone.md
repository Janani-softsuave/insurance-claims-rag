# Claims Triage & Coverage Assistant (Week 12 Capstone — Track D)

Triages one insurance claim end to end: fetches the FNOL record, checks whether coverage was
in force on the loss date, retrieves the policy wording that was actually in effect on that
date (not today's), and refers the claim to a human adjuster with the cited clause,
endorsement version, and the deductible/sub-limit/policy-limit kept as three separate
numbers. **It never states a coverage decision — that's a code-enforced rule, not a prompt
request.**

## Run it (one command)

```bash
pip install -r requirements.txt
python -m app.ingestion.pipeline   # or: python -c "from app.ingestion.pipeline import ingest; ingest(reset=True)"
python -m scripts.run_capstone CLM-2027-00310
```

That's it. No subcommand verb (the CLI collapses to its one command — pass the claim number
directly, see `analysis/week12/seam_list.md` item 3 if you're curious why).

You need a `GEMINI_API_KEY` in `.env` (copy `.env.example`). The free tier is capped at 20
requests/day/project/model — if you hit that, the client waits an hour and retries
automatically; you don't need to do anything, just let it run (see `cost_by_stage.md` and
`tenx.md` for why this matters at scale).

## What you'll see

```
discovered tools: ['get_claim', 'check_coverage_in_force', 'search_policy_wording',
                    'compute_amounts', 'refer_to_adjuster']

trace_id: <one id, present in every span logged for this request>
iterations: <N>  tokens: <N>  cost: $<N>

tool calls:
  [claims-triage-coverage] get_claim({'claim_number': 'CLM-2027-00310'})
  [claims-triage-coverage] check_coverage_in_force({...})
  [claims-triage-coverage] search_policy_wording({..., 'loss_date': '2024-08-11'})
  [claims-triage-coverage] compute_amounts({...})
  [claims-triage-coverage] refer_to_adjuster({...})

final (referral, not a decision):
{
  "claim_number": "CLM-2027-00310",
  "coverage_signal": "supports_coverage",
  "cited_clause": "Clause 7(a)",
  "endorsement_version": "2023-R1",
  "loss_date_resolved_against": "2024-08-11",
  ...
}
```

Try a claim with a loss date on the other side of 2025-01-01 (e.g. `CLM-2027-00311`) and the
same tool call resolves against `2025-R1` instead — same code path, the date decided it.

## Picking any other claim

All 25 claims live in `analysis/week12/claims_corpus.json`. Pick any `claim_number` from
there.

## Everything else lives in `analysis/week12/`

| File | What it is |
|---|---|
| `seam_list.md` | Every integration friction point found, unedited, fixed/accepted/ran-out-of-time |
| `architecture.md` | The one-page sketch: boxes, arrows, where the model calls happen, where the money goes |
| `known_weaknesses.md` | Top 3 weaknesses, written before the eval suite ran |
| `eval_report.md` | Full eval-suite output on the integrated system, judge agreement, stated non-coverage |
| `error_taxonomy.md` | Re-scored failure modes, frequencies, severities, trace ids, the mode integration created |
| `trajectory_eval.md` | Tool-choice accuracy and the outcome-vs-trajectory gap |
| `trace.json` | One real end-to-end trace, cost/latency per span, trace id across both hops |
| `cost_by_stage.md` | Cost per claim triaged, broken down by stage |
| `tenx.md` | What breaks first at 18,000 FNOLs/week, with the number |
| `fresh_eyes_note.md` | Who ran it cold, where they stumbled, what changed as a result |
| `demo_script.md` | The 10-minute, four-part demo script |

## What this system deliberately does NOT do

- It does not decide coverage. `coverage_signal` is `supports_coverage` / `supports_exclusion`
  / `ambiguous` — the MCP server rejects the literal word "covered" anywhere in the referral
  summary, by code, not by prompt.
- It does not log or return claimant PII. `get_claim`'s MCP response redacts names, addresses,
  and labelled-name patterns before it ever leaves the server process.
- It does not rewrite the ~60-page base policy corpus — only two small, explicitly-dated
  exclusion-schedule documents were added (see `seam_list.md` item 7) so the loss-date-aware
  retrieval mechanism has two genuinely different, dated versions to resolve between.
