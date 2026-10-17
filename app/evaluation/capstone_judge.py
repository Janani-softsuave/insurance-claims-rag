from __future__ import annotations

import time

import instructor
from google import genai
from pydantic import BaseModel, Field

from app.core.config import ROOT_DIR, settings
from app.core.logging import get_logger

logger = get_logger(__name__)

JUDGE_PROMPT_PATH = ROOT_DIR / "analysis" / "week12" / "judge_prompt_v1.txt"


class CapstoneJudgeVerdict(BaseModel):
    faithful: bool = Field(
        description="True only if the referral's coverage_signal, cited clause, endorsement "
        "version, and distinct money figures are all faithfully supported by the retrieved "
        "policy text and claim facts, and the summary does not state a coverage decision."
    )
    rationale: str = Field(description="One sentence explaining the verdict.")


def _build_user_prompt(claim: dict, search_results: list[dict], final: dict) -> str:
    policy_text = "\n\n---\n\n".join(
        f"[endorsement_version={c.get('endorsement_version')}] {c['source']}\n{c['text']}" for c in search_results
    )
    return (
        f"FNOL/ADJUSTER NOTES (redacted): {claim['fnol_text']} {claim['adjuster_notes']}\n"
        f"LOSS DATE: {claim['loss_date']}\n\n"
        f"RETRIEVED POLICY TEXT:\n{policy_text}\n\n"
        f"SYSTEM REFERRAL OUTPUT:\n"
        f"coverage_signal: {final.get('coverage_signal')}\n"
        f"cited_clause: {final.get('cited_clause')}\n"
        f"endorsement_version: {final.get('endorsement_version')}\n"
        f"deductible: {final.get('deductible')}  sub_limit: {final.get('sub_limit')}  policy_limit: {final.get('policy_limit')}\n"
        f"summary: {final.get('summary')}\n\n"
        "Judge this referral now."
    )


ALL_KEYS_WAIT_SECONDS = 3600.0


class CapstoneJudge:
    def __init__(self, api_key: str | None = None, model: str | None = None):
        self._key_pool = [api_key] if api_key else settings.gemini_api_key_pool()
        if not self._key_pool:
            self._key_pool = [""]
        self._key_index = 0
        self.model = model or settings.gemini_model
        self.system_prompt = JUDGE_PROMPT_PATH.read_text(encoding="utf-8")
        self.client = instructor.from_genai(genai.Client(api_key=self._key_pool[self._key_index]))

    def _rotate_key(self) -> None:
        self._key_index = (self._key_index + 1) % len(self._key_pool)
        self.client = instructor.from_genai(genai.Client(api_key=self._key_pool[self._key_index]))

    def judge(self, claim: dict, search_results: list[dict], final: dict) -> CapstoneJudgeVerdict:
        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": _build_user_prompt(claim, search_results, final)},
        ]
        tried_this_cycle = 0
        while True:
            try:
                return self.client.chat.completions.create(
                    model=self.model,
                    response_model=CapstoneJudgeVerdict,
                    max_retries=1,
                    messages=messages,
                )
            except Exception as exc:
                msg = str(exc)
                is_quota = "RESOURCE_EXHAUSTED" in msg or "429" in msg
                is_overload = "UNAVAILABLE" in msg or "503" in msg
                if not (is_quota or is_overload):
                    raise
                tried_this_cycle += 1
                if tried_this_cycle < len(self._key_pool):
                    logger.warning("Judge key %d/%d exhausted, rotating.", self._key_index + 1, len(self._key_pool))
                    self._rotate_key()
                    continue
                logger.warning("All %d judge key(s) exhausted — sleeping %.0fs then retrying all keys.", len(self._key_pool), ALL_KEYS_WAIT_SECONDS)
                time.sleep(ALL_KEYS_WAIT_SECONDS)
                tried_this_cycle = 0
