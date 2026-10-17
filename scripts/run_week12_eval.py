from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from contextlib import contextmanager

from app.agent.budgets import Budgets
from app.agent.capstone_prompt import CAPSTONE_SYSTEM_PROMPT
from app.agent.capstone_tools import load_claims
from app.core.config import ROOT_DIR
from app.evaluation.capstone_assertions import run_capstone_assertions
from app.evaluation.capstone_judge import CapstoneJudge
from app.mcp_agent.agent import MCPAgent

WEEK12_DIR = ROOT_DIR / "analysis" / "week12"
CAPSTONE_CONFIG_PATH = ROOT_DIR / "mcp_config.capstone.json"
RESULTS_PATH = WEEK12_DIR / "eval_results.json"

RACE_BUDGETS = Budgets(max_iterations=8, max_tokens=30_000, max_cost_usd=0.05, max_wall_clock_seconds=999_999.0)

ALL_KEYS_WAIT_SECONDS = 3600.0


def _pid_is_alive(pid: int) -> bool:
    if sys.platform == "win32":
        import subprocess

        out = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}"], capture_output=True, text=True
        ).stdout
        return str(pid) in out
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


@contextmanager
def _single_instance_lock(name: str):
    """Refuses to run if another instance (by lock file + still-alive pid) is already
    running. Two instances racing on the same checkpoint file silently drop each other's
    writes, and both burn API quota re-doing the same claims."""
    lock_path = WEEK12_DIR / f".{name}.lock"
    if lock_path.exists():
        try:
            other_pid = int(lock_path.read_text(encoding="utf-8").strip())
        except (ValueError, OSError):
            other_pid = None
        if other_pid and _pid_is_alive(other_pid):
            print(f"Another {name} instance is already running (pid {other_pid}). Exiting.")
            raise SystemExit(1)
    WEEK12_DIR.mkdir(parents=True, exist_ok=True)
    lock_path.write_text(str(os.getpid()), encoding="utf-8")
    try:
        yield
    finally:
        lock_path.unlink(missing_ok=True)


def _load_results() -> dict:
    if RESULTS_PATH.exists():
        return json.loads(RESULTS_PATH.read_text(encoding="utf-8"))
    return {}


def _save_results(results: dict) -> None:
    RESULTS_PATH.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")


def _judge_with_retry(judge: CapstoneJudge, claim: dict, search_results: list[dict], final: dict):
    same_cycle_attempts = 0
    max_same_cycle_attempts = 6
    cycle = 0
    while True:
        try:
            return judge.judge(claim, search_results, final)
        except Exception as exc:
            msg = str(exc)
            is_transient = "RESOURCE_EXHAUSTED" in msg or "429" in msg or "UNAVAILABLE" in msg or "503" in msg
            if not is_transient:
                raise
            if same_cycle_attempts < max_same_cycle_attempts:
                same_cycle_attempts += 1
                delay = min(60, 5 * same_cycle_attempts)
                print(f"judge: transient error (attempt {same_cycle_attempts}/{max_same_cycle_attempts}), backing off {delay}s")
                time.sleep(delay)
                continue
            cycle += 1
            print(f"judge: still failing after {max_same_cycle_attempts} attempts (cycle {cycle}) — sleeping {ALL_KEYS_WAIT_SECONDS:.0f}s.")
            time.sleep(ALL_KEYS_WAIT_SECONDS)
            same_cycle_attempts = 0


async def _run_one(agent: MCPAgent, claim: dict) -> dict:
    result = await agent.run(claim["claim_number"])
    return {
        "claim_number": claim["claim_number"],
        "trace_id": result.trace_id,
        "iterations": result.iterations,
        "total_tokens": result.total_tokens,
        "total_cost_usd": result.total_cost_usd,
        "tool_calls": result.tool_calls,
        "final": result.final,
        "terminated_by_budget": result.terminated_by_budget,
        "log": result.log,
    }


async def _main_async() -> None:
    claims = {c["claim_number"]: c for c in load_claims()}
    results = _load_results()

    agent = MCPAgent(budgets=RACE_BUDGETS, system_prompt=CAPSTONE_SYSTEM_PROMPT, config_path=CAPSTONE_CONFIG_PATH)
    await agent.connect()
    try:
        for cn, claim in claims.items():
            if cn in results and results[cn].get("final") is not None:
                continue
            print(f"running {cn}...")
            r = await _run_one(agent, claim)
            results[cn] = r
            _save_results(results)
            print(cn, "-> final:", json.dumps(r["final"], ensure_ascii=False)[:200])
    finally:
        await agent.close()

    print(f"\nDone. {sum(1 for r in results.values() if r.get('final'))} / {len(claims)} claims produced a referral.")


def run_judging() -> None:
    claims = {c["claim_number"]: c for c in load_claims()}
    results = _load_results()
    judge = CapstoneJudge()
    judge_results_path = WEEK12_DIR / "judge_results.json"
    judge_results = json.loads(judge_results_path.read_text(encoding="utf-8")) if judge_results_path.exists() else {}

    from app.agent.capstone_tools import search_policy_wording

    for cn, r in results.items():
        if cn in judge_results or not r.get("final"):
            continue
        claim = claims[cn]
        chunks = search_policy_wording(claim["fnol_text"], claim["loss_date"], top_k=4)["chunks"]
        verdict = _judge_with_retry(judge, claim, chunks, r["final"])
        judge_results[cn] = {"faithful": verdict.faithful, "rationale": verdict.rationale}
        judge_results_path.write_text(json.dumps(judge_results, indent=2, ensure_ascii=False), encoding="utf-8")
        print(cn, "-> faithful:", verdict.faithful, "-", verdict.rationale)

    n = len(judge_results)
    agree = sum(1 for v in judge_results.values() if v["faithful"])
    print(f"\nJudged {n} cases, {agree} faithful.")


if __name__ == "__main__":
    import typer

    app = typer.Typer()

    @app.command()
    def agent_runs() -> None:
        with _single_instance_lock("agent_runs"):
            asyncio.run(_main_async())

    @app.command()
    def judge_runs() -> None:
        with _single_instance_lock("judge_runs"):
            run_judging()

    app()
