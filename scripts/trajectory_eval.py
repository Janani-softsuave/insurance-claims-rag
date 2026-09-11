from __future__ import annotations

import json
import re
import statistics
from dataclasses import asdict

import typer
from rich.console import Console
from rich.table import Table

from app.agent.budgets import Budgets
from app.agent.claims_agent import MITIGATED_SYSTEM_PROMPT, SYSTEM_PROMPT, ClaimsAgent
from app.agent.tools import load_claims
from app.core.config import ROOT_DIR

app = typer.Typer(help="Week 8 — trajectory eval for the claims agent.")
console = Console()

WEEK8_DIR = ROOT_DIR / "analysis" / "week8"
WEEK7_CLAIMS_PATH = ROOT_DIR / "analysis" / "week7" / "claims.json"

TRAJ_BUDGETS = Budgets(max_iterations=8, max_tokens=30_000, max_cost_usd=0.05, max_wall_clock_seconds=90.0)

SYSTEM_PROMPTS = {"baseline": SYSTEM_PROMPT, "mitigated": MITIGATED_SYSTEM_PROMPT}

# Requirement 1: expected tool sequences per claim. Claims whose adjuster notes
# raise no coverage question that policy text could answer (needs_policy_lookup
# is false in claims.json) legitimately accept a shorter path OR a diligence
# search_policy call — both are asserted as a set, not a single sequence.
# CLM-2027-00205 additionally accepts an optional check_claim_history call
# (before or after search_policy) because it carries IMT-28 Zero Dep cover,
# the one claim where a per-year endorsement cap is actually in play.
EXPECTED_PATHS: dict[str, dict] = {
    "CLM-2027-00201": {
        "paths": {("get_claim", "search_policy", "compute_payout", "submit_decision")},
        "min_steps": 4,
    },
    "CLM-2027-00202": {
        "paths": {
            ("get_claim", "compute_payout", "submit_decision"),
            ("get_claim", "search_policy", "compute_payout", "submit_decision"),
        },
        "min_steps": 3,
    },
    "CLM-2027-00203": {
        "paths": {("get_claim", "search_policy", "compute_payout", "submit_decision")},
        "min_steps": 4,
    },
    "CLM-2027-00204": {
        "paths": {
            ("get_claim", "compute_payout", "submit_decision"),
            ("get_claim", "search_policy", "compute_payout", "submit_decision"),
        },
        "min_steps": 3,
    },
    "CLM-2027-00205": {
        "paths": {
            ("get_claim", "search_policy", "compute_payout", "submit_decision"),
            ("get_claim", "search_policy", "check_claim_history", "compute_payout", "submit_decision"),
            ("get_claim", "check_claim_history", "search_policy", "compute_payout", "submit_decision"),
        },
        "min_steps": 4,
    },
    "CLM-2027-00206": {
        "paths": {("get_claim", "search_policy", "compute_payout", "submit_decision")},
        "min_steps": 4,
    },
    "CLM-2027-00207": {
        "paths": {("get_claim", "search_policy", "compute_payout", "submit_decision")},
        "min_steps": 4,
    },
    "CLM-2027-00208": {
        "paths": {("get_claim", "search_policy", "compute_payout", "submit_decision")},
        "min_steps": 4,
    },
    "CLM-2027-00209": {
        "paths": {("get_claim", "search_policy", "compute_payout", "submit_decision")},
        "min_steps": 4,
    },
    "CLM-2027-00210": {
        "paths": {
            ("get_claim", "compute_payout", "submit_decision"),
            ("get_claim", "search_policy", "compute_payout", "submit_decision"),
        },
        "min_steps": 3,
    },
}

REPEAT_CHECK_TOOLS = {"get_claim", "search_policy", "compute_payout", "check_claim_history"}
CODE_PATTERN = re.compile(r"\bIMT-\d+\b|\bIAP-\d+\b")


def _allowed_universe(claim_number: str) -> set[str]:
    universe: set[str] = {"submit_decision"}
    for path in EXPECTED_PATHS[claim_number]["paths"]:
        universe.update(path)
    return universe


def _grade_outcome(expected_status: str, expected_payout: float, status: str | None, payout: float | None) -> bool:
    if status != expected_status:
        return False
    if payout is None:
        return False
    return abs(payout - expected_payout) < 1.0


def _load_claims() -> dict[str, dict]:
    return {c["claim_number"]: c for c in json.loads(WEEK7_CLAIMS_PATH.read_text(encoding="utf-8"))}


def _results_path(variant: str):
    return WEEK8_DIR / f"trajectory_{variant}.json"


def _load_results(variant: str) -> dict:
    path = _results_path(variant)
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {}


def _save_results(variant: str, results: dict) -> None:
    _results_path(variant).write_text(json.dumps(results, indent=2, default=str), encoding="utf-8")


@app.command()
def run(variant: str = typer.Option("baseline", help="baseline | mitigated"), regenerate: bool = typer.Option(False)) -> None:
    """Run the agent over the 10 Week 7 claims, checkpointed per claim, capturing full trajectories."""
    if variant not in SYSTEM_PROMPTS:
        raise typer.BadParameter("variant must be 'baseline' or 'mitigated'")

    WEEK8_DIR.mkdir(parents=True, exist_ok=True)
    results = {} if regenerate else _load_results(variant)
    claims = load_claims()

    agent = ClaimsAgent(budgets=TRAJ_BUDGETS, system_prompt=SYSTEM_PROMPTS[variant])

    for claim in claims:
        cn = claim["claim_number"]
        if cn in results:
            continue
        console.print(f"[dim]{variant}[/dim] {cn}...")
        try:
            result = agent.run(cn)
        except Exception as exc:
            console.print(f"[red]{cn} failed ({exc.__class__.__name__}) — stopping, checkpoint preserved.[/red]")
            _save_results(variant, results)
            raise
        results[cn] = asdict(result)
        _save_results(variant, results)

    console.print(f"[green]Done. {len(results)}/10 claims captured for variant={variant}.[/green]")


def _score_claim(cn: str, r: dict, claim_record: dict) -> dict:
    trajectory = r["trajectory"]
    names = [e["tool"] for e in trajectory]
    universe = _allowed_universe(cn)
    accepted_paths = EXPECTED_PATHS[cn]["paths"]
    min_steps = EXPECTED_PATHS[cn]["min_steps"]

    data_calls = [e for e in trajectory if e["tool"] not in ("submit_decision", "flag_for_review")]
    terminal_calls = [e for e in trajectory if e["tool"] in ("submit_decision", "flag_for_review")]

    canonical: list[str] = []
    seen: set[str] = set()
    for name in [e["tool"] for e in data_calls]:
        if name not in seen:
            canonical.append(name)
            seen.add(name)
    if terminal_calls:
        canonical.append(terminal_calls[-1]["tool"])
    canonical_t = tuple(canonical)

    decision_reached = bool(terminal_calls) and r.get("terminated_by_budget") is None and terminal_calls[-1]["tool"] == "submit_decision"
    terminal_wrong = bool(terminal_calls) and terminal_calls[-1]["tool"] == "flag_for_review"

    counts: dict[str, int] = {}
    for e in data_calls:
        counts[e["tool"]] = counts.get(e["tool"], 0) + 1
    repeats_violation = any(counts.get(t, 0) > 1 for t in REPEAT_CHECK_TOOLS)

    wrong_tool_present = any(name not in universe for name in names)

    seen2: set[str] = set()
    scored_calls = []
    for e in data_calls:
        name = e["tool"]
        if name not in universe:
            scored_calls.append((name, False))
        elif name in seen2:
            scored_calls.append((name, False))
        else:
            scored_calls.append((name, True))
        seen2.add(name)
    if terminal_calls:
        scored_calls.append((terminal_calls[-1]["tool"], terminal_calls[-1]["tool"] == "submit_decision"))

    checkable = 0
    valid = 0
    invalid_details: list[str] = []
    search_text = " ".join(
        chunk.get("text", "")
        for e in trajectory
        if e["tool"] == "search_policy" and isinstance(e.get("result"), list)
        for chunk in e["result"]
    )
    last_payout = None
    for e in trajectory:
        name, args, result = e["tool"], e["args"], e.get("result")
        if name == "get_claim":
            checkable += 1
            if args.get("claim_number") == cn:
                valid += 1
            else:
                invalid_details.append(f"get_claim fetched {args.get('claim_number')!r} instead of {cn!r}")
        elif name == "check_claim_history":
            checkable += 1
            if args.get("policy_id") == claim_record["policy_id"]:
                valid += 1
            else:
                invalid_details.append(
                    f"check_claim_history used policy_id={args.get('policy_id')!r}, real policy_id is {claim_record['policy_id']!r}"
                )
        elif name == "compute_payout":
            checkable += 1
            ok = args.get("claimed_amount") == claim_record["claimed_amount"] and args.get("excess_amount") in (
                claim_record["excess_amount"],
                0,
            )
            if ok:
                valid += 1
            else:
                invalid_details.append(
                    f"compute_payout args {args} inconsistent with claim record "
                    f"(claimed_amount={claim_record['claimed_amount']}, excess_amount={claim_record['excess_amount']})"
                )
            if isinstance(result, dict):
                last_payout = result.get("payout")
        elif name in ("submit_decision", "flag_for_review"):
            checkable += 1
            rationale = args.get("rationale") or args.get("reason") or ""
            codes = set(CODE_PATTERN.findall(rationale))
            hallucinated = [c for c in codes if c not in search_text]
            payout_arg = args.get("payout")
            payout_consistent = last_payout is None or payout_arg is None or abs(payout_arg - last_payout) < 1.0
            if not hallucinated and payout_consistent:
                valid += 1
            else:
                if hallucinated:
                    invalid_details.append(f"rationale cites {hallucinated} never seen in retrieved policy text")
                if not payout_consistent:
                    invalid_details.append(f"submitted payout {payout_arg} != last compute_payout result {last_payout}")

    args_ok = not invalid_details

    if not decision_reached:
        mode = "loop_no_decision"
    elif terminal_wrong:
        mode = "premature_escalation"
    elif wrong_tool_present:
        mode = "wrong_tool"
    elif not args_ok:
        mode = "hallucinated_argument"
    elif repeats_violation:
        mode = "redundant_tool_loop"
    elif canonical_t not in accepted_paths:
        mode = "unexpected_path"
    else:
        mode = "none"

    steps_taken = len(trajectory)
    step_efficiency = steps_taken / min_steps if min_steps else None

    return {
        "claim_number": cn,
        "actual_sequence": names,
        "canonical": canonical_t,
        "accepted_paths": sorted(accepted_paths),
        "mode": mode,
        "trajectory_pass": mode == "none",
        "scored_calls": scored_calls,
        "checkable_arg_calls": checkable,
        "valid_arg_calls": valid,
        "invalid_arg_details": invalid_details,
        "steps_taken": steps_taken,
        "min_steps": min_steps,
        "step_efficiency": step_efficiency,
        "cost_usd": r["total_cost_usd"],
        "tokens": r["total_tokens"],
        "latency_s": r["elapsed_seconds"],
        "outcome_status": r["status"],
        "outcome_payout": r["payout"],
    }


@app.command()
def report(variant: str = typer.Option("baseline")) -> None:
    """Compute the four trajectory numbers, the outcome-vs-trajectory gap, and the named case."""
    results = _load_results(variant)
    claims_by_number = _load_claims()
    if len(results) < 10:
        console.print(f"[yellow]Only {len(results)}/10 claims captured for variant={variant} — run `run` first.[/yellow]")

    scored = []
    for cn, r in results.items():
        scored.append(_score_claim(cn, r, claims_by_number[cn]))

    total_calls = sum(len(s["scored_calls"]) for s in scored)
    correct_calls = sum(sum(1 for _, ok in s["scored_calls"] if ok) for s in scored)
    tool_choice_accuracy = correct_calls / total_calls if total_calls else 0.0

    total_checkable = sum(s["checkable_arg_calls"] for s in scored)
    total_valid = sum(s["valid_arg_calls"] for s in scored)
    argument_validity_rate = total_valid / total_checkable if total_checkable else 0.0

    step_effs = [s["step_efficiency"] for s in scored if s["step_efficiency"] is not None]
    mean_step_efficiency = statistics.mean(step_effs) if step_effs else 0.0

    costs = [s["cost_usd"] for s in scored]
    cost_p50 = statistics.median(costs) if costs else 0.0
    cost_max = max(costs) if costs else 0.0

    outcome_pass = {
        s["claim_number"]: _grade_outcome(
            claims_by_number[s["claim_number"]]["expected_status"],
            claims_by_number[s["claim_number"]]["expected_payout"],
            s["outcome_status"],
            s["outcome_payout"],
        )
        for s in scored
    }
    outcome_pass_rate = sum(outcome_pass.values()) / len(scored) if scored else 0.0
    trajectory_pass_rate = sum(s["trajectory_pass"] for s in scored) / len(scored) if scored else 0.0
    gap = outcome_pass_rate - trajectory_pass_rate

    mode_counts: dict[str, int] = {}
    for s in scored:
        mode_counts[s["mode"]] = mode_counts.get(s["mode"], 0) + 1

    table = Table(title=f"Week 8 trajectory eval — {variant}")
    table.add_column("Claim")
    table.add_column("Outcome", justify="center")
    table.add_column("Trajectory", justify="center")
    table.add_column("Mode")
    table.add_column("Steps taken/needed", justify="right")
    table.add_column("Cost (USD)", justify="right")
    for s in sorted(scored, key=lambda x: x["claim_number"]):
        cn = s["claim_number"]
        table.add_row(
            cn,
            "✅" if outcome_pass[cn] else "❌",
            "✅" if s["trajectory_pass"] else "❌",
            s["mode"],
            f"{s['steps_taken']}/{s['min_steps']}",
            f"${s['cost_usd']:.6f}",
        )
    console.print(table)

    summary = Table(title="Trajectory numbers")
    summary.add_column("Metric")
    summary.add_column("Value", justify="right")
    summary.add_row("Tool-choice accuracy", f"{tool_choice_accuracy:.1%}")
    summary.add_row("Argument validity rate", f"{argument_validity_rate:.1%}")
    summary.add_row("Step efficiency (mean, steps taken/needed)", f"{mean_step_efficiency:.2f}x")
    summary.add_row("Cost per claim — p50", f"${cost_p50:.6f}")
    summary.add_row("Cost per claim — max", f"${cost_max:.6f}")
    summary.add_row("Outcome pass rate", f"{outcome_pass_rate:.0%}")
    summary.add_row("Trajectory pass rate", f"{trajectory_pass_rate:.0%}")
    summary.add_row("Outcome-vs-trajectory gap", f"{gap:+.0%}")
    console.print(summary)

    mode_table = Table(title="Failure mode counts")
    mode_table.add_column("Mode")
    mode_table.add_column("Count", justify="right")
    for mode, count in sorted(mode_counts.items(), key=lambda kv: -kv[1]):
        mode_table.add_row(mode, str(count))
    console.print(mode_table)

    named_case = next(
        (s for s in scored if outcome_pass[s["claim_number"]] and not s["trajectory_pass"]),
        None,
    )
    if named_case:
        console.print(
            f"\n[bold]Named right-answer-wrong-path case:[/bold] {named_case['claim_number']} "
            f"— outcome passed ({named_case['outcome_status']}, payout {named_case['outcome_payout']}) "
            f"but trajectory failed ({named_case['mode']}).\n"
            f"Actual sequence: {named_case['actual_sequence']}\n"
            f"Accepted paths: {named_case['accepted_paths']}"
        )
        if named_case["invalid_arg_details"]:
            console.print(f"Argument issues: {named_case['invalid_arg_details']}")

    report_out = {
        "variant": variant,
        "tool_choice_accuracy": tool_choice_accuracy,
        "argument_validity_rate": argument_validity_rate,
        "mean_step_efficiency": mean_step_efficiency,
        "cost_p50_usd": cost_p50,
        "cost_max_usd": cost_max,
        "outcome_pass_rate": outcome_pass_rate,
        "trajectory_pass_rate": trajectory_pass_rate,
        "gap": gap,
        "mode_counts": mode_counts,
        "named_case": named_case,
        "per_claim": scored,
    }
    (WEEK8_DIR / f"report_{variant}.json").write_text(json.dumps(report_out, indent=2, default=str), encoding="utf-8")
    console.print(f"\n[green]Wrote {WEEK8_DIR / f'report_{variant}.json'}[/green]")


@app.command()
def compare(before: str = typer.Option("baseline"), after: str = typer.Option("mitigated")) -> None:
    """Regression check: per-mode counts before -> after, and the price paid."""
    before_path = WEEK8_DIR / f"report_{before}.json"
    after_path = WEEK8_DIR / f"report_{after}.json"
    if not before_path.exists() or not after_path.exists():
        console.print("[red]Run `report` for both variants first.[/red]")
        raise typer.Exit(1)

    b = json.loads(before_path.read_text(encoding="utf-8"))
    a = json.loads(after_path.read_text(encoding="utf-8"))

    all_modes = sorted(set(b["mode_counts"]) | set(a["mode_counts"]))
    table = Table(title=f"Regression check — {before} -> {after}")
    table.add_column("Mode")
    table.add_column("Before", justify="right")
    table.add_column("After", justify="right")
    table.add_column("Delta", justify="right")
    worsened = []
    new_modes = []
    for mode in all_modes:
        bc = b["mode_counts"].get(mode, 0)
        ac = a["mode_counts"].get(mode, 0)
        delta = ac - bc
        table.add_row(mode, str(bc), str(ac), f"{delta:+d}")
        if delta > 0:
            worsened.append(mode)
        if bc == 0 and ac > 0:
            new_modes.append(mode)
    console.print(table)

    if worsened:
        console.print(f"[yellow]Modes that got worse: {worsened}[/yellow]")
    else:
        console.print("[green]No mode got worse.[/green]")
    if new_modes:
        console.print(f"[yellow]New modes introduced by the mitigation: {new_modes}[/yellow]")

    price = Table(title="Price paid by the mitigation")
    price.add_column("Metric")
    price.add_column(before, justify="right")
    price.add_column(after, justify="right")
    price.add_column("Delta", justify="right")
    price.add_row("Cost per claim p50 (USD)", f"${b['cost_p50_usd']:.6f}", f"${a['cost_p50_usd']:.6f}", f"{a['cost_p50_usd'] - b['cost_p50_usd']:+.6f}")
    price.add_row("Cost per claim max (USD)", f"${b['cost_max_usd']:.6f}", f"${a['cost_max_usd']:.6f}", f"{a['cost_max_usd'] - b['cost_max_usd']:+.6f}")
    price.add_row("Mean step efficiency", f"{b['mean_step_efficiency']:.2f}x", f"{a['mean_step_efficiency']:.2f}x", f"{a['mean_step_efficiency'] - b['mean_step_efficiency']:+.2f}x")
    price.add_row("Outcome pass rate", f"{b['outcome_pass_rate']:.0%}", f"{a['outcome_pass_rate']:.0%}", f"{a['outcome_pass_rate'] - b['outcome_pass_rate']:+.0%}")
    price.add_row("Trajectory pass rate", f"{b['trajectory_pass_rate']:.0%}", f"{a['trajectory_pass_rate']:.0%}", f"{a['trajectory_pass_rate'] - b['trajectory_pass_rate']:+.0%}")
    console.print(price)


if __name__ == "__main__":
    app()
