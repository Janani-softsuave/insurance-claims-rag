from __future__ import annotations

import json
import time

from app.agent.claims_workflow import ClaimsWorkflow
from app.agent.tools import load_claims
from app.core.config import ROOT_DIR

WEEK11_DIR = ROOT_DIR / "analysis" / "week11"
RESULTS_PATH = WEEK11_DIR / "post_fix_suite_results.json"

ALL_KEYS_WAIT_SECONDS = 3600.0
USERS = ["adjuster_03", "adjuster_08", "adjuster_14", "adjuster_19", "adjuster_27"]


def _load_results() -> dict:
    if RESULTS_PATH.exists():
        return json.loads(RESULTS_PATH.read_text(encoding="utf-8"))
    return {}


def _save_results(results: dict) -> None:
    RESULTS_PATH.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")


def _run_with_retry(wf: ClaimsWorkflow, cn: str, user: str) -> dict:
    same_cycle_attempts = 0
    max_same_cycle_attempts = 6
    cycle = 0
    while True:
        try:
            return wf.run(cn, user=user, input_type="claim_number_lookup")
        except Exception as exc:
            msg = str(exc)
            is_quota_or_overload = "RESOURCE_EXHAUSTED" in msg or "429" in msg or "UNAVAILABLE" in msg or "503" in msg
            if not is_quota_or_overload:
                raise
            if same_cycle_attempts < max_same_cycle_attempts:
                same_cycle_attempts += 1
                delay = min(60, 5 * same_cycle_attempts)
                print(f"{cn}: transient error (attempt {same_cycle_attempts}/{max_same_cycle_attempts}), backing off {delay}s")
                time.sleep(delay)
                continue
            cycle += 1
            print(f"{cn}: still failing after {max_same_cycle_attempts} attempts (cycle {cycle}) — sleeping {ALL_KEYS_WAIT_SECONDS:.0f}s then retrying.")
            time.sleep(ALL_KEYS_WAIT_SECONDS)
            same_cycle_attempts = 0


def main() -> None:
    WEEK11_DIR.mkdir(parents=True, exist_ok=True)
    claims = {c["claim_number"]: c for c in load_claims()}
    results = _load_results()
    wf = ClaimsWorkflow()

    for i, cn in enumerate(claims):
        if cn in results:
            continue
        print(f"running {cn}...")
        r = _run_with_retry(wf, cn, user=USERS[i % len(USERS)])
        exp = claims[cn]
        passed = (
            r["status"] == exp["expected_status"]
            and r["payout"] is not None
            and abs(r["payout"] - exp["expected_payout"]) < 1.0
        )
        results[cn] = {**r, "pass": passed, "expected_status": exp["expected_status"], "expected_payout": exp["expected_payout"]}
        _save_results(results)
        print(cn, "PASS" if passed else "FAIL", "| got", r["status"], r["payout"], "| expected", exp["expected_status"], exp["expected_payout"])

    n = len(results)
    p = sum(r["pass"] for r in results.values())
    print()
    print(f"POST-FIX SUITE: {p}/{n} pass")


if __name__ == "__main__":
    main()
