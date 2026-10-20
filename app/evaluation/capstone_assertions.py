from __future__ import annotations

import json

from app.core.config import ROOT_DIR

WEEK12_DIR = ROOT_DIR / "analysis" / "week12"
POLICY_LIMITS = json.loads((WEEK12_DIR / "policy_limits.json").read_text(encoding="utf-8"))

FLOOD_REASON_CODES = {
    "COVERED_FLOOD_2023_WORDING",
    "DENIED_FLOOD_2025_WORDING_NO_RIDER",
}


def _expected_endorsement_version(loss_date: str) -> str:
    return "2023-R1" if loss_date <= "2024-12-31" else "2025-R1"


def assert_no_covered_word(final: dict) -> bool:
    import re

    summary = (final or {}).get("summary", "") or ""
    return not bool(re.search(r"\bcovered\b", summary, re.IGNORECASE))

def assert_coverage_signal_valid(final: dict) -> bool:
    return (final or {}).get("coverage_signal") in ("supports_coverage", "supports_exclusion", "ambiguous")


def assert_three_distinct_figures(final: dict, product: str) -> bool:
    if not final:
        return False
    limits = POLICY_LIMITS.get(product, {})
    deductible_ok = final.get("deductible") == limits.get("deductible")
    sub_limit_ok = final.get("sub_limit") == limits.get("sub_limit")
    policy_limit_ok = bool(final.get("policy_limit"))
    return deductible_ok and sub_limit_ok and policy_limit_ok


def assert_coverage_in_force_checked_before_referral(tool_calls: list[dict]) -> bool:
    names = [tc["tool"] for tc in tool_calls]
    if "check_coverage_in_force" not in names or "refer_to_adjuster" not in names:
        return False
    return names.index("check_coverage_in_force") < names.index("refer_to_adjuster")


def assert_loss_date_used_in_search(tool_calls: list[dict], claim_loss_date: str) -> bool:
    """Vacuously true when no search_policy_wording call was made at all — a lapsed policy
    correctly skips the search entirely (see CAPSTONE_SYSTEM_PROMPT step 2), and that is not
    a failure of this assertion. This checks only that WHEN a search did happen, it used the
    claim's real loss_date rather than inventing or defaulting to another one."""
    search_calls = [tc for tc in tool_calls if tc["tool"] == "search_policy_wording"]
    if not search_calls:
        return True
    return all(tc["args"].get("loss_date") == claim_loss_date for tc in search_calls)


def assert_correct_endorsement_version_if_flood(final: dict, reason_code: str, loss_date: str) -> bool:
    if reason_code not in FLOOD_REASON_CODES:
        return True
    if not final:
        return False
    return final.get("endorsement_version") == _expected_endorsement_version(loss_date)


def run_capstone_assertions(claim: dict, final: dict | None, tool_calls: list[dict]) -> dict[str, bool]:
    return {
        "no_covered_word": assert_no_covered_word(final or {}),
        "coverage_signal_valid": assert_coverage_signal_valid(final or {}),
        "three_distinct_figures": assert_three_distinct_figures(final or {}, claim["product"]),
        "coverage_in_force_checked_before_referral": assert_coverage_in_force_checked_before_referral(tool_calls),
        "loss_date_used_in_search": assert_loss_date_used_in_search(tool_calls, claim["loss_date"]),
        "correct_endorsement_version_if_flood": assert_correct_endorsement_version_if_flood(
            final or {}, claim["reason_code"], claim["loss_date"]
        ),
    }
