from __future__ import annotations

import csv
import json
import statistics

import typer
from rich.console import Console
from rich.table import Table

from app.agent.budgets import Budgets
from app.agent.claims_agent import ClaimsAgent
from app.agent.claims_workflow import ClaimsWorkflow
from app.agent.tools import load_claims, search_policy
from app.core.config import ROOT_DIR

app = typer.Typer(help="Week 7 — race the claims agent against the fixed workflow.")
console = Console()

WEEK7_DIR = ROOT_DIR / "analysis" / "week7"
RESULTS_PATH = WEEK7_DIR / "race_results.json"
RACE_CSV_PATH = WEEK7_DIR / "race.csv"
PER_CLAIM_CSV_PATH = WEEK7_DIR / "race_per_claim.csv"

RACE_BUDGETS = Budgets(max_iterations=8, max_tokens=30_000, max_cost_usd=0.05, max_wall_clock_seconds=90.0)


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
    return {"workflow": {}, "agent": {}}


def _save_results(results: dict) -> None:
    RESULTS_PATH.write_text(json.dumps(results, indent=2), encoding="utf-8")


@app.command()
def race(regenerate: bool = typer.Option(False, help="Ignore any existing checkpoint and start over.")) -> None:
    """Run both systems over the same 10 claims, checkpointed per claim."""
    if regenerate and RESULTS_PATH.exists():
        RESULTS_PATH.unlink()

    results = _load_results()
    claims = load_claims()
    _warm_up()

    workflow = ClaimsWorkflow()
    agent = ClaimsAgent(budgets=RACE_BUDGETS)

    for claim in claims:
        cn = claim["claim_number"]

        if cn not in results["workflow"]:
            console.print(f"[dim]workflow[/dim] {cn}...")
            try:
                r = workflow.run(cn)
            except Exception as exc:
                console.print(f"[red]workflow {cn} failed ({exc.__class__.__name__}) — stopping, checkpoint preserved.[/red]")
                _write_reports(results, claims, partial=True)
                raise
            r["pass"] = _grade(claim["expected_status"], claim["expected_payout"], r["status"], r["payout"])
            results["workflow"][cn] = r
            _save_results(results)

        if cn not in results["agent"]:
            console.print(f"[dim]agent[/dim] {cn}...")
            try:
                ar = agent.run(cn)
            except Exception as exc:
                console.print(f"[red]agent {cn} failed ({exc.__class__.__name__}) — stopping, checkpoint preserved.[/red]")
                _write_reports(results, claims, partial=True)
                raise
            r = {
                "claim_number": cn,
                "status": ar.status,
                "payout": ar.payout,
                "rationale": ar.rationale,
                "total_tokens": ar.total_tokens,
                "total_cost_usd": ar.total_cost_usd,
                "elapsed_seconds": ar.elapsed_seconds,
                "tool_calls": ar.tool_calls,
                "terminated_by_budget": ar.terminated_by_budget,
            }
            r["pass"] = _grade(claim["expected_status"], claim["expected_payout"], r["status"], r["payout"])
            results["agent"][cn] = r
            _save_results(results)

    _write_reports(results, claims)


def _write_reports(results: dict, claims: list[dict], partial: bool = False) -> None:
    with PER_CLAIM_CSV_PATH.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["claim_number", "needs_policy_lookup", "system", "status", "payout", "pass", "tokens", "cost_usd", "latency_s"])
        for claim in claims:
            cn = claim["claim_number"]
            for system in ("workflow", "agent"):
                r = results[system].get(cn)
                if r is None:
                    continue
                writer.writerow(
                    [cn, claim["needs_policy_lookup"], system, r["status"], r["payout"], r["pass"], r["total_tokens"], round(r["total_cost_usd"], 6), round(r["elapsed_seconds"], 2)]
                )

    summary = {}
    for system in ("workflow", "agent"):
        rows = list(results[system].values())
        n = len(rows)
        if n == 0:
            continue
        pass_rate = sum(r["pass"] for r in rows) / n
        p50_latency = statistics.median(r["elapsed_seconds"] for r in rows)
        total_tokens = sum(r["total_tokens"] for r in rows)
        cost_per_claim = sum(r["total_cost_usd"] for r in rows) / n
        summary[system] = {
            "n": n,
            "pass_rate": pass_rate,
            "p50_latency_s": p50_latency,
            "total_tokens": total_tokens,
            "cost_per_claim_usd": cost_per_claim,
        }

    with RACE_CSV_PATH.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["system", "n_claims", "pass_rate", "p50_latency_s", "total_tokens", "cost_per_claim_usd"])
        for system, s in summary.items():
            writer.writerow([system, s["n"], f"{s['pass_rate']:.2f}", f"{s['p50_latency_s']:.2f}", s["total_tokens"], f"{s['cost_per_claim_usd']:.6f}"])

    title = "Week 7 Race — Agent vs Workflow" + (" (PARTIAL — a run failed mid-race)" if partial else "")
    table = Table(title=title)
    table.add_column("System")
    table.add_column("Pass rate", justify="right")
    table.add_column("p50 latency (s)", justify="right")
    table.add_column("Total tokens", justify="right")
    table.add_column("Cost/claim (USD)", justify="right")
    for system, s in summary.items():
        table.add_row(system, f"{s['pass_rate']:.0%}", f"{s['p50_latency_s']:.2f}", str(s["total_tokens"]), f"${s['cost_per_claim_usd']:.6f}")
    console.print(table)


@app.command("budget-demo")
def budget_demo(claim_number: str = typer.Option("CLM-2027-00201"), max_iterations: int = typer.Option(2)) -> None:
    """Run the agent with a deliberately tight budget to demonstrate clean termination."""
    tight_budgets = Budgets(max_iterations=max_iterations, max_tokens=30_000, max_cost_usd=0.05, max_wall_clock_seconds=300.0)
    agent = ClaimsAgent(budgets=tight_budgets)
    result = agent.run(claim_number)

    lines = [
        f"Budget demo — claim {claim_number}, max_iterations={max_iterations}",
        f"terminated_by_budget: {result.terminated_by_budget}",
        f"final status: {result.status}  payout: {result.payout}",
        f"iterations used: {result.iterations}  tokens: {result.total_tokens}  cost: ${result.total_cost_usd:.6f}",
        "",
        "--- log ---",
        *result.log,
    ]
    log_path = WEEK7_DIR / "budget_termination_log.txt"
    log_path.write_text("\n".join(lines), encoding="utf-8")
    console.print(f"[green]Wrote {log_path}[/green]")
    for line in lines:
        console.print(line)


if __name__ == "__main__":
    app()
