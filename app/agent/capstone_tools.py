from __future__ import annotations

import json
from functools import lru_cache
from typing import Literal

from google.genai import types

from app.core.config import ROOT_DIR
from app.ingestion.doc_metadata import date_to_int
from app.retrieval.reranker import get_reranker
from app.retrieval.retriever import Retriever

WEEK12_DIR = ROOT_DIR / "analysis" / "week12"
CLAIMS_PATH = WEEK12_DIR / "claims_corpus.json"
POLICY_LIMITS_PATH = WEEK12_DIR / "policy_limits.json"
COVERAGE_IN_FORCE_PATH = WEEK12_DIR / "coverage_in_force.json"

CoverageSignal = Literal["supports_coverage", "supports_exclusion", "ambiguous"]


@lru_cache
def _claims_store() -> dict[str, dict]:
    records = json.loads(CLAIMS_PATH.read_text(encoding="utf-8"))
    return {r["claim_number"]: r for r in records}


@lru_cache
def _policy_limits() -> dict[str, dict]:
    return json.loads(POLICY_LIMITS_PATH.read_text(encoding="utf-8"))


@lru_cache
def _coverage_in_force() -> dict[str, dict]:
    return json.loads(COVERAGE_IN_FORCE_PATH.read_text(encoding="utf-8"))


def load_claims() -> list[dict]:
    return list(_claims_store().values())


def get_claim(claim_number: str) -> dict:
    record = _claims_store().get(claim_number)
    if record is None:
        return {"error": f"No claim found with number '{claim_number}'."}
    limits = _policy_limits().get(record["product"], {})
    return {
        "claim_number": record["claim_number"],
        "policy_number": record["policy_number"],
        "product": record["product"],
        "loss_date": record["loss_date"],
        "claimed_amount": record["claimed_amount"],
        "fnol_text": record["fnol_text"],
        "adjuster_notes": record["adjuster_notes"],
        "photo_caption": record["photo_caption"],
        "deductible": limits.get("deductible"),
        "sub_limit": limits.get("sub_limit"),
        "policy_limit": limits.get("policy_limit"),
    }


def check_coverage_in_force(policy_number: str, loss_date: str) -> dict:
    window = _coverage_in_force().get(policy_number)
    if window is None:
        return {"error": f"No coverage-in-force record for policy '{policy_number}'."}
    in_force = window["start_date"] <= loss_date <= window["end_date"]
    return {
        "policy_number": policy_number,
        "loss_date": loss_date,
        "coverage_start_date": window["start_date"],
        "coverage_end_date": window["end_date"],
        "in_force": in_force,
    }


@lru_cache
def _retriever() -> Retriever:
    return Retriever()


def search_policy_wording(query: str, loss_date: str, top_k: int = 4) -> dict:
    """Date-scoped policy search. `where` enforces the date filter in code —
    only chunks whose effective_from/effective_to window contains loss_date are
    ever considered, before reranking ever runs. This is not a prompt hint."""
    loss_date_int = date_to_int(loss_date)
    where = {
        "$and": [
            {"effective_from_int": {"$lte": loss_date_int}},
            {"effective_to_int": {"$gte": loss_date_int}},
        ]
    }
    dense_pool_size = max(top_k * 2, 8)
    candidates = _retriever().retrieve(query, top_k=dense_pool_size, where=where)
    reranked = get_reranker().rerank(query, candidates, top_n=min(4, top_k))
    return {
        "loss_date": loss_date,
        "chunks": [
            {
                "source": rc.chunk.source,
                "chunk_index": rc.chunk.chunk_index,
                "text": rc.chunk.text.strip(),
                "endorsement_version": rc.chunk.metadata.get("endorsement_version", "base"),
                "effective_from": rc.chunk.metadata.get("effective_from"),
                "effective_to": rc.chunk.metadata.get("effective_to"),
            }
            for rc in reranked
        ],
    }


def compute_amounts(claimed_amount: float, deductible: float, sub_limit: float | None = None) -> dict:
    """Pure arithmetic, kept distinct and separate — never collapsed into one number.
    This tool does NOT decide coverage; it only computes what each distinct figure
    would be if an adjuster applies them, for the adjuster's reference."""
    payable_before_sub_limit = max(claimed_amount - deductible, 0.0)
    payable_after_sub_limit = (
        min(payable_before_sub_limit, sub_limit) if sub_limit is not None else payable_before_sub_limit
    )
    return {
        "claimed_amount": claimed_amount,
        "deductible": deductible,
        "sub_limit": sub_limit,
        "payable_before_sub_limit": payable_before_sub_limit,
        "payable_after_sub_limit": payable_after_sub_limit,
        "note": "These are reference figures for the adjuster, not a coverage decision.",
    }


def refer_to_adjuster(
    claim_number: str,
    coverage_signal: CoverageSignal,
    cited_clause: str,
    endorsement_version: str,
    loss_date_resolved_against: str,
    deductible: float,
    policy_limit: str,
    summary: str,
    sub_limit: float | None = None,
) -> dict:
    """Terminal action. ALWAYS refers to a human adjuster — never a coverage
    decision. `coverage_signal` states what the cited policy text supports, not
    what happens to the claim; `supports_coverage` is not the same as 'covered'
    and must never be rendered as that word anywhere downstream."""
    return {
        "claim_number": claim_number,
        "action": "referred_to_adjuster",
        "coverage_signal": coverage_signal,
        "cited_clause": cited_clause,
        "endorsement_version": endorsement_version,
        "loss_date_resolved_against": loss_date_resolved_against,
        "deductible": deductible,
        "sub_limit": sub_limit,
        "policy_limit": policy_limit,
        "summary": summary,
    }


GET_CLAIM_DECLARATION = types.FunctionDeclaration(
    name="get_claim",
    description=(
        "Fetch the stored FNOL/claim record for one claim by its claim number: policy number, "
        "product, loss date, claimed amount, FNOL text, adjuster notes, photo caption, and the "
        "policy's deductible/sub-limit/policy-limit figures. Call this first for any claim you "
        "don't already have data for."
    ),
    parameters={
        "type": "object",
        "properties": {"claim_number": {"type": "string"}},
        "required": ["claim_number"],
    },
)

CHECK_COVERAGE_IN_FORCE_DECLARATION = types.FunctionDeclaration(
    name="check_coverage_in_force",
    description=(
        "Check whether the policy's coverage was in force on the loss date. This is the only "
        "tool that returns the policy's coverage start/end dates — call it before deciding "
        "anything else, since a lapsed policy on the loss date changes everything downstream."
    ),
    parameters={
        "type": "object",
        "properties": {
            "policy_number": {"type": "string"},
            "loss_date": {"type": "string", "description": "ISO date, e.g. 2024-08-11."},
        },
        "required": ["policy_number", "loss_date"],
    },
)

SEARCH_POLICY_WORDING_DECLARATION = types.FunctionDeclaration(
    name="search_policy_wording",
    description=(
        "Search the insurer's policy wording and exclusions schedule for text relevant to a "
        "described loss, SCOPED to the endorsement version in force on the given loss_date — the "
        "date filter is enforced by this tool itself, not by asking you to pick the right "
        "document. Always pass the claim's actual loss_date, never today's date."
    ),
    parameters={
        "type": "object",
        "properties": {
            "query": {"type": "string"},
            "loss_date": {"type": "string", "description": "ISO date the loss occurred, e.g. 2024-08-11."},
        },
        "required": ["query", "loss_date"],
    },
)

COMPUTE_AMOUNTS_DECLARATION = types.FunctionDeclaration(
    name="compute_amounts",
    description=(
        "Compute the reference payable amount before and after any sub-limit, given the claimed "
        "amount, deductible, and sub-limit (null if none applies). Deductible, sub-limit, and "
        "policy limit must always be reported as three distinct figures — never collapse them "
        "into one number. This tool does not decide coverage."
    ),
    parameters={
        "type": "object",
        "properties": {
            "claimed_amount": {"type": "number"},
            "deductible": {"type": "number"},
            "sub_limit": {"type": "number", "description": "Omit entirely if no sub-limit applies to this claim."},
        },
        "required": ["claimed_amount", "deductible"],
    },
)

REFER_TO_ADJUSTER_DECLARATION = types.FunctionDeclaration(
    name="refer_to_adjuster",
    description=(
        "End the task by referring this claim to a human adjuster with your findings. Call this "
        "exactly once, last, ALWAYS — this system never states a coverage decision itself, only "
        "surfaces the facts and cited wording. coverage_signal must be 'supports_coverage', "
        "'supports_exclusion', or 'ambiguous' — never the word 'covered'. Cite the exact clause "
        "AND the endorsement version it came from, and the loss_date you resolved it against."
    ),
    parameters={
        "type": "object",
        "properties": {
            "claim_number": {"type": "string"},
            "coverage_signal": {"type": "string", "enum": ["supports_coverage", "supports_exclusion", "ambiguous"]},
            "cited_clause": {"type": "string", "description": "e.g. 'Clause 9(a)'."},
            "endorsement_version": {"type": "string", "description": "e.g. '2023-R1' or '2025-R1'."},
            "loss_date_resolved_against": {"type": "string"},
            "deductible": {"type": "number"},
            "sub_limit": {"type": "number", "description": "Omit entirely if no sub-limit applies to this claim."},
            "policy_limit": {"type": "string"},
            "summary": {"type": "string", "description": "One or two sentences for the adjuster, no verdict word."},
        },
        "required": [
            "claim_number", "coverage_signal", "cited_clause", "endorsement_version",
            "loss_date_resolved_against", "deductible", "policy_limit", "summary",
        ],
    },
)

CAPSTONE_TOOLS = types.Tool(
    function_declarations=[
        GET_CLAIM_DECLARATION,
        CHECK_COVERAGE_IN_FORCE_DECLARATION,
        SEARCH_POLICY_WORDING_DECLARATION,
        COMPUTE_AMOUNTS_DECLARATION,
        REFER_TO_ADJUSTER_DECLARATION,
    ]
)

CAPSTONE_TOOL_IMPLS = {
    "get_claim": get_claim,
    "check_coverage_in_force": check_coverage_in_force,
    "search_policy_wording": search_policy_wording,
    "compute_amounts": compute_amounts,
}
