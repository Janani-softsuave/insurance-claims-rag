# Injected worker failure — CLM-2027-00206

The coverage/exclusions worker's LLM call was made to raise a simulated 500
(`WorkerFailure` in `app/agent/orchestrator.py`, `inject_exclusions_failure_for`)
on both the first call and the retry for this one claim — a persistent, not
transient, upstream failure.

## What the orchestrator actually did

1. Manager called the exclusions worker — injected 500.
2. Manager retried once — injected 500 again (not recoverable via retry).
3. Manager degraded: it did NOT call the synthesis LLM at all, and did NOT ask the
   summary worker to guess coverage. It went straight to `flag_for_review`, citing
   the exclusions check as unavailable.

Actual behaviour: **degraded** (escalated to a human adjuster rather than deciding
coverage with one specialist missing).

Expected status for this claim was `denied` (payout $0). The orchestrator returned `flagged_for_review` — which fails the pass/fail judge on this one claim, and
that's the honest cost of the injected failure: it is counted against the
multi-agent arm's pass rate above, not hidden.

The alternative this avoided: letting the manager synthesise a decision from the
summary worker's output alone and rounding an unknown coverage question up to
"covered" — exactly the wrongful-coverage-statement trap the task brief names
under Common Mistakes. Escalating a claim nobody can currently evaluate is a defensible
outcome; guessing coverage on a burglary claim whose exclusion check never ran is not.
