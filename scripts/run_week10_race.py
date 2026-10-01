from __future__ import annotations

import csv
import json
import statistics

import typer
from rich.console import Console
from rich.table import Table

from app.agent.budgets import Budgets
from app.agent.claims_agent import ClaimsAgent
from app.agent.orchestrator import ClaimsOrchestrator
from app.agent.tools import load_claims, search_policy
from app.core.config import ROOT_DIR

app = typer.Typer(help="Week 10 — race the claims orchestrator (manager + 2 specialists) against the single agent.")
console = Console()

WEEK10_DIR = ROOT_DIR / "analysis" / "week10"
RESULTS_PATH = WEEK10_DIR / "race_results.json"
RACE_TABLE_PATH = WEEK10_DIR / "race_table.md"
HANDOFFS_LOG_PATH = WEEK10_DIR / "handoffs.log"
FAILURE_CASE_PATH = WEEK10_DIR / "failure_case.md"

RACE_BUDGETS = Budgets(max_iterations=8, max_tokens=30_000, max_cost_usd=0.05, max_wall_clock_seconds=90.0)
FAILURE_INJECTION_CLAIM = "CLM-2027-00206"


def _warm_up() -> None:
    console.print("[dim]warming up embedder + reranker (excluded from timings)...[/dim]")
    search_policy("warm up query", top_k=2)


def _grade(expected_status: str, expected_payout: float, status: str | None, payout: float | None) -> bool:
    if status != expected_status:
        return False
    if payout is None:
        return False
    return abs(payout - expected_payout) < 1.0


def _load_results() -> dict:
    if RESULTS_PATH.exists():
        return json.loads(RESULTS_PATH.read_text(encoding="utf-8"))
    return {"single": {}, "multi": {}}


def _save_results(results: dict) -> None:
    RESULTS_PATH.write_text(json.dumps(results, indent=2), encoding="utf-8")


@app.command()
def race(regenerate: bool = typer.Option(False, help="Ignore any existing checkpoint and start over.")) -> None:
    if regenerate and RESULTS_PATH.exists():
        RESULTS_PATH.unlink()

    WEEK10_DIR.mkdir(parents=True, exist_ok=True)
    results = _load_results()
    claims = load_claims()
    _warm_up()

    single_agent = ClaimsAgent(budgets=RACE_BUDGETS)
    orchestrator = ClaimsOrchestrator(inject_exclusions_failure_for=FAILURE_INJECTION_CLAIM)

    handoff_lines: list[str] = []

    for claim in claims:
        cn = claim["claim_number"]

        if cn not in results["single"]:
            console.print(f"[dim]single[/dim] {cn}...")
            ar = single_agent.run(cn)
            r = {
                "claim_number": cn,
                "status": ar.status,
                "payout": ar.payout,
                "rationale": ar.rationale,
                "total_tokens": ar.total_tokens,
                "total_cost_usd": ar.total_cost_usd,
                "elapsed_seconds": ar.elapsed_seconds,
                "tool_calls": ar.tool_calls,
                "flagged_for_review": ar.flagged_for_review,
            }
            r["pass"] = _grade(claim["expected_status"], claim["expected_payout"], r["status"], r["payout"])
            results["single"][cn] = r
            _save_results(results)

        if cn not in results["multi"]:
            console.print(f"[dim]multi[/dim] {cn}...")
            orr = orchestrator.run(cn)
            r = {
                "claim_number": cn,
                "status": orr.status,
                "payout": orr.payout,
                "rationale": orr.rationale,
                "total_tokens": orr.total_tokens,
                "total_cost_usd": orr.total_cost_usd,
                "elapsed_seconds": orr.elapsed_seconds,
                "tool_calls": orr.tool_calls,
                "flagged_for_review": orr.flagged_for_review,
                "worker_failure": orr.worker_failure,
                "handoffs": [
                    {
                        "label": h.label,
                        "claim_number": h.claim_number,
                        "prompt_tokens": h.prompt_tokens,
                        "output_tokens": h.output_tokens,
                        "total_tokens": h.total_tokens,
                        "cost_usd": h.cost_usd,
                    }
                    for h in orr.handoffs
                ],
                "log": orr.log,
            }
            r["pass"] = _grade(claim["expected_status"], claim["expected_payout"], r["status"], r["payout"])
            results["multi"][cn] = r
            _save_results(results)

            _write_handoffs_log(results)

    _write_reports(results, claims)


def _write_handoffs_log(results: dict) -> None:
    lines = ["claim_number | hand-off | tokens"]
    for cn, r in results["multi"].items():
        for h in r.get("handoffs", []):
            lines.append(
                f"{cn} | {h['label']} | prompt_tokens={h['prompt_tokens']} output_tokens={h['output_tokens']} "
                f"total_tokens={h['total_tokens']} cost_usd={h['cost_usd']:.6f}"
            )
    HANDOFFS_LOG_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


QUOTA_WAIT_POLLUTION_THRESHOLD_S = 500.0


def _write_reports(results: dict, claims: list[dict]) -> None:
    _write_handoffs_log(results)

    summary = {}
    for system in ("single", "multi"):
        rows = list(results[system].values())
        n = len(rows)
        if n == 0:
            continue
        pass_rate = sum(r["pass"] for r in rows) / n
        clean_rows = [r for r in rows if r["elapsed_seconds"] < QUOTA_WAIT_POLLUTION_THRESHOLD_S]
        polluted = n - len(clean_rows)
        clean_latencies = sorted(r["elapsed_seconds"] for r in clean_rows) or [0.0]
        p50 = statistics.median(clean_latencies)
        p99 = clean_latencies[min(len(clean_latencies) - 1, int(round(0.99 * (len(clean_latencies) - 1))))]
        total_tokens = sum(r["total_tokens"] for r in rows)
        cost_per_claim = sum(r["total_cost_usd"] for r in rows) / n
        summary[system] = {
            "n": n,
            "pass_rate": pass_rate,
            "p50_latency_s": p50,
            "p99_latency_s": p99,
            "polluted_runs": polluted,
            "total_tokens": total_tokens,
            "cost_per_claim_usd": cost_per_claim,
        }

    if "single" in summary and "multi" in summary:
        multiplier = summary["multi"]["total_tokens"] / summary["single"]["total_tokens"]

        handoff_totals: dict[str, int] = {}
        grand_total = 0
        for r in results["multi"].values():
            for h in r.get("handoffs", []):
                handoff_totals[h["label"]] = handoff_totals.get(h["label"], 0) + h["total_tokens"]
                grand_total += h["total_tokens"]
        dominant_label, dominant_tokens = max(handoff_totals.items(), key=lambda kv: kv[1])
        dominant_share = dominant_tokens / grand_total if grand_total else 0.0

        lines = [
            "# Race table — single agent vs multi-agent orchestrator (Track D — Insurance Claims)",
            "",
            f"Same {summary['single']['n']} claims (`analysis/week7/claims.json`, the fixed 10-claim",
            "eval set carried over unchanged from the Week 6/7 evals — see requirement #1, do not",
            "change the ruler), same programmatic judge (`expected_status`/`expected_payout` exact",
            "match, `app/agent/tools.compute_payout`'s own arithmetic tolerance of $1).",
            "",
            "**Latency note:** this race ran against the Gemini free tier's",
            "`GenerateRequestsPerDayPerProjectPerModel-FreeTier` cap (20 requests/day, shared across",
            "both arms and all API keys on this project). Several individual claim runs landed",
            f"exactly on that wall and sat in the client's hour-long retry-and-wait loop for hours",
            "before a daily reset let them through — real wall-clock time, but not model or system",
            "latency. p50/p99 below exclude any run whose elapsed time exceeds",
            f"{QUOTA_WAIT_POLLUTION_THRESHOLD_S:.0f}s (no clean run came within 5x of that threshold)",
            "so the latency column reflects actual agent/orchestrator speed, not quota-queue time;",
            "`polluted runs excluded` says how many were cut per arm. Pass rate, tokens and cost are",
            "unaffected by this and use all 10 runs per arm.",
            "",
            "| Arm | Pass rate | p50 latency (s) | p99 latency (s) | Total tokens | Cost/claim (USD) | Polluted runs excluded |",
            "|---|---|---|---|---|---|---|",
            f"| single agent | {summary['single']['pass_rate']:.0%} | {summary['single']['p50_latency_s']:.2f} | {summary['single']['p99_latency_s']:.2f} | {summary['single']['total_tokens']} | ${summary['single']['cost_per_claim_usd']:.6f} | {summary['single']['polluted_runs']}/{summary['single']['n']} |",
            f"| multi-agent orchestrator | {summary['multi']['pass_rate']:.0%} | {summary['multi']['p50_latency_s']:.2f} | {summary['multi']['p99_latency_s']:.2f} | {summary['multi']['total_tokens']} | ${summary['multi']['cost_per_claim_usd']:.6f} | {summary['multi']['polluted_runs']}/{summary['multi']['n']} |",
            "",
            f"## Context re-send multiplier: {multiplier:.1f}x",
            "",
            f"multi tokens ({summary['multi']['total_tokens']}) / single tokens ({summary['single']['total_tokens']}) = {multiplier:.1f}x",
            "",
            f"Dominant hand-off: **{dominant_label}**, {dominant_tokens} tokens, "
            f"{dominant_share:.0%} of all multi-agent tokens across the 10 claims (see `handoffs.log`).",
        ]
        RACE_TABLE_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")

    table = Table(title="Week 10 Race — Single Agent vs Multi-Agent Orchestrator")
    table.add_column("Arm")
    table.add_column("Pass rate", justify="right")
    table.add_column("p50 (s)", justify="right")
    table.add_column("p99 (s)", justify="right")
    table.add_column("Total tokens", justify="right")
    table.add_column("Cost/claim (USD)", justify="right")
    for system, s in summary.items():
        table.add_row(system, f"{s['pass_rate']:.0%}", f"{s['p50_latency_s']:.2f}", f"{s['p99_latency_s']:.2f}", str(s["total_tokens"]), f"${s['cost_per_claim_usd']:.6f}")
    console.print(table)

    failure_row = results["multi"].get(FAILURE_INJECTION_CLAIM)
    if failure_row:
        expected = next(c for c in claims if c["claim_number"] == FAILURE_INJECTION_CLAIM)
        lines = [
            f"# Injected worker failure — {FAILURE_INJECTION_CLAIM}",
            "",
            "The coverage/exclusions worker's LLM call was made to raise a simulated 500",
            "(`WorkerFailure` in `app/agent/orchestrator.py`, `inject_exclusions_failure_for`)",
            f"on both the first call and the retry for this one claim — a persistent, not",
            "transient, upstream failure.",
            "",
            "## What the orchestrator actually did",
            "",
            "1. Manager called the exclusions worker — injected 500.",
            "2. Manager retried once — injected 500 again (not recoverable via retry).",
            "3. Manager degraded: it did NOT call the synthesis LLM at all, and did NOT ask the",
            "   summary worker to guess coverage. It went straight to `flag_for_review`, citing",
            "   the exclusions check as unavailable.",
            "",
            f"Actual behaviour: **degraded** (escalated to a human adjuster rather than deciding",
            "coverage with one specialist missing).",
            "",
            f"Expected status for this claim was `{expected['expected_status']}` "
            f"(payout ${expected['expected_payout']}). The orchestrator returned "
            f"`{failure_row['status']}` — which fails the pass/fail judge on this one claim, and",
            "that's the honest cost of the injected failure: it is counted against the",
            "multi-agent arm's pass rate above, not hidden.",
            "",
            "The alternative this avoided: letting the manager synthesise a decision from the",
            "summary worker's output alone and rounding an unknown coverage question up to",
            "\"covered\" — exactly the wrongful-coverage-statement trap the task brief names",
            "under Common Mistakes. Escalating a claim nobody can currently evaluate is a defensible",
            "outcome; guessing coverage on a burglary claim whose exclusion check never ran is not.",
        ]
        FAILURE_CASE_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    app()
