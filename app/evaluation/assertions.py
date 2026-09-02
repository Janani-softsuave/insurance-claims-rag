from __future__ import annotations

import re
from datetime import datetime

from dateutil import parser as date_parser

from app.models.schemas import ClaimSummary

_CLAIM_NUMBER_RE = re.compile(r"^CLM-\d{4}-\d{5}$")
_EMPTY_CLAUSE_VALUES = {"", "n/a", "na", "none", "not applicable", "unknown"}


def assert_claim_number_format(summary: ClaimSummary) -> bool:
    return bool(_CLAIM_NUMBER_RE.match(summary.claim_number.strip()))


def assert_date_of_loss_parseable(summary: ClaimSummary) -> bool:
    try:
        parsed = date_parser.parse(summary.date_of_loss, fuzzy=False)
        return isinstance(parsed, datetime)
    except (ValueError, OverflowError, TypeError):
        return False


def assert_excess_numeric(summary: ClaimSummary) -> bool:
    return isinstance(summary.excess_amount, (int, float)) and summary.excess_amount >= 0


def assert_exclusion_cited_on_denial(summary: ClaimSummary) -> bool:
    if summary.coverage_decision != "denied":
        return True
    clause = (summary.exclusion_clause_id or "").strip().lower()
    return clause not in _EMPTY_CLAUSE_VALUES


ASSERTIONS = {
    "claim_number_format": assert_claim_number_format,
    "date_of_loss_parseable": assert_date_of_loss_parseable,
    "excess_numeric": assert_excess_numeric,
    "exclusion_cited_on_denial": assert_exclusion_cited_on_denial,
}


def run_assertions(summary: ClaimSummary) -> dict[str, bool]:
    return {name: fn(summary) for name, fn in ASSERTIONS.items()}
