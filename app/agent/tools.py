from __future__ import annotations

import json
from functools import lru_cache
from typing import Literal

from google.genai import types

from app.core.config import ROOT_DIR
from app.retrieval.reranker import get_reranker
from app.retrieval.retriever import Retriever

CLAIMS_PATH = ROOT_DIR / "analysis" / "week7" / "claims.json"
CLAIM_HISTORY_PATH = ROOT_DIR / "analysis" / "week7" / "claim_history.json"

ClaimStatus = Literal["covered", "denied", "partial", "pending"]


@lru_cache
def _claims_store() -> dict[str, dict]:
    records = json.loads(CLAIMS_PATH.read_text(encoding="utf-8"))
    return {r["claim_number"]: r for r in records}


@lru_cache
def _history_store() -> dict[str, dict]:
    return json.loads(CLAIM_HISTORY_PATH.read_text(encoding="utf-8"))


def get_claim(claim_number: str) -> dict:
    record = _claims_store().get(claim_number)
    if record is None:
        return {"error": f"No claim found with number '{claim_number}'."}
    return {
        "claim_number": record["claim_number"],
        "policy_id": record["policy_id"],
        "sum_insured": record["sum_insured"],
        "excess_amount": record["excess_amount"],
        "claimed_amount": record["claimed_amount"],
        "adjuster_notes": record["adjuster_notes"],
    }


@lru_cache
def _retriever() -> Retriever:
    return Retriever()


def search_policy(query: str, top_k: int = 4) -> list[dict]:
    candidates = _retriever().retrieve(query, top_k=top_k)
    reranked = get_reranker().rerank(query, candidates, top_n=min(4, top_k))
    return [
        {"source": rc.chunk.source, "chunk_index": rc.chunk.chunk_index, "text": rc.chunk.text.strip()}
        for rc in reranked
    ]


def check_claim_history(policy_id: str) -> dict:
    record = _history_store().get(policy_id)
    if record is None:
        return {"error": f"No claim history found for policy '{policy_id}'."}
    return {"policy_id": policy_id, **record}


def compute_payout(claim_status: ClaimStatus, claimed_amount: float, excess_amount: float) -> dict:
    if claim_status in ("denied", "pending"):
        payout = 0.0
    elif claim_status == "covered":
        payout = max(claimed_amount - excess_amount, 0.0)
    elif claim_status == "partial":
        payout = round(max((claimed_amount - excess_amount) * 0.5, 0.0), 2)
    else:
        return {"error": f"Unknown claim_status '{claim_status}'."}
    return {"payout": payout}


GET_CLAIM_DECLARATION = types.FunctionDeclaration(
    name="get_claim",
    description=(
        "Fetch the stored record for one claim by its claim number: sum insured, excess amount, "
        "claimed amount, and the adjuster's raw notes. This is the only tool that returns claim "
        "records — use it first for any claim you don't already have data for."
    ),
    parameters={
        "type": "object",
        "properties": {
            "claim_number": {"type": "string", "description": "The claim number, e.g. CLM-2027-00201."},
        },
        "required": ["claim_number"],
    },
)

SEARCH_POLICY_DECLARATION = types.FunctionDeclaration(
    name="search_policy",
    description=(
        "Search the insurer's policy wording and endorsement documents for text relevant to a "
        "described incident or coverage question, and return the most relevant passages. This is "
        "the only tool that searches policy document text — use it to check whether a peril, "
        "exclusion, or endorsement applies to what the adjuster notes describe."
    ),
    parameters={
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "A natural-language description of the incident or coverage question."},
        },
        "required": ["query"],
    },
)

COMPUTE_PAYOUT_DECLARATION = types.FunctionDeclaration(
    name="compute_payout",
    description=(
        "Compute the payout amount owed for a claim, given a coverage decision you have already "
        "made and the claimed and excess amounts. This is the only tool that does payout "
        "arithmetic — it does not fetch claim records or search policy text, and it does not "
        "decide coverage itself. Call it only after you have already determined claim_status "
        "from the claim record and any relevant policy text."
    ),
    parameters={
        "type": "object",
        "properties": {
            "claim_status": {
                "type": "string",
                "enum": ["covered", "denied", "partial", "pending"],
                "description": (
                    "covered = fully payable; denied = not payable, an exclusion applies; "
                    "partial = payable at a reduced rate (e.g. a depreciation exception); "
                    "pending = not yet payable, a required document or condition is outstanding."
                ),
            },
            "claimed_amount": {"type": "number", "description": "The amount claimed."},
            "excess_amount": {
                "type": "number",
                "description": (
                    "The excess/deductible that actually applies to this payout. Usually the "
                    "claim record's excess_amount, but pass 0 if policy text shows the deductible "
                    "is waived for this specific claim."
                ),
            },
        },
        "required": ["claim_status", "claimed_amount", "excess_amount"],
    },
)

CHECK_CLAIM_HISTORY_DECLARATION = types.FunctionDeclaration(
    name="check_claim_history",
    description=(
        "Look up how many claims a policy has already had this policy year, including "
        "endorsement-specific counts (IMT-28 Zero Dep claims, IMT-40 roadside assistance events), "
        "so you can check per-year caps such as 'IMT-28 is capped at 2 claims per policy year'. "
        "This is the only tool that returns claim-frequency history — it does not fetch this "
        "claim's own details or search policy text."
    ),
    parameters={
        "type": "object",
        "properties": {
            "policy_id": {"type": "string", "description": "The policy id from the claim record, e.g. MOTOR-COMP-03."},
        },
        "required": ["policy_id"],
    },
)

FLAG_FOR_REVIEW_DECLARATION = types.FunctionDeclaration(
    name="flag_for_review",
    description=(
        "End the task by escalating this claim to a human adjuster instead of deciding it "
        "yourself, when the claim record and policy text together are not enough to confidently "
        "determine coverage (for example, genuinely contradictory or missing policy guidance). "
        "Call this exactly once, instead of submit_decision, only when you cannot responsibly "
        "decide. This is a finish action, not a data tool."
    ),
    parameters={
        "type": "object",
        "properties": {
            "claim_number": {"type": "string"},
            "reason": {"type": "string", "description": "Why this claim needs a human, in one or two sentences."},
        },
        "required": ["claim_number", "reason"],
    },
)

SUBMIT_DECISION_DECLARATION = types.FunctionDeclaration(
    name="submit_decision",
    description=(
        "Submit your final decision for this claim and end the task. Call this exactly once, "
        "only after you have fetched the claim, checked policy text if needed, and computed the "
        "payout. This is the task's finish action, not a data tool."
    ),
    parameters={
        "type": "object",
        "properties": {
            "claim_number": {"type": "string"},
            "claim_status": {"type": "string", "enum": ["covered", "denied", "partial", "pending"]},
            "payout": {"type": "number"},
            "rationale": {"type": "string", "description": "One or two sentences explaining the decision."},
        },
        "required": ["claim_number", "claim_status", "payout", "rationale"],
    },
)

AGENT_TOOLS = types.Tool(
    function_declarations=[
        GET_CLAIM_DECLARATION,
        SEARCH_POLICY_DECLARATION,
        COMPUTE_PAYOUT_DECLARATION,
        CHECK_CLAIM_HISTORY_DECLARATION,
        SUBMIT_DECISION_DECLARATION,
        FLAG_FOR_REVIEW_DECLARATION,
    ]
)

TOOL_IMPLS = {
    "get_claim": get_claim,
    "search_policy": search_policy,
    "compute_payout": compute_payout,
    "check_claim_history": check_claim_history,
}


def load_claims() -> list[dict]:
    return list(_claims_store().values())
