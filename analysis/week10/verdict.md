Verdict: KEEP the multi-agent orchestrator (Track D — Insurance Claims).
It wins all four numbers: 80% pass rate vs single-agent's 70%, $0.000583/claim vs $0.000988,
69,324 total tokens vs 126,629, and faster p50/p99 once quota-wait sleeps are excluded (see race_table.md).
Sunk-cost bias, named out loud: this race took four days of wall-clock time on a 20-req/day free key —
that effort is not evidence the orchestrator is better; the verdict is argued from the numbers alone.
Caveat cutting the other way: 3 of the single agent's 4 wrong answers were clean 90s wall-clock budget
terminations whose clock ran through the same quota-wait sleeps, so 70% may undercount its real capability;
the orchestrator carries no equivalent budget and avoided that artifact.
Where the orchestrator lost quality: CLM-2027-00207 paid $3,500 instead of $4,500 because its exclusions
worker's narrow prompt never asks about deductible waivers — the narrow-prompt tradeoff the brief warns about.
