from __future__ import annotations

from pathlib import Path

import instructor
from google import genai
from pydantic import BaseModel, Field

from app.core.config import settings, ROOT_DIR
from app.core.logging import get_logger
from app.models.schemas import ClaimSummary, RetrievedChunk

logger = get_logger(__name__)

JUDGE_PROMPTS_DIR = ROOT_DIR / "analysis" / "week6"


class JudgeVerdict(BaseModel):
    faithful: bool = Field(
        description="True only if every coverage-relevant claim in the summary is directly "
        "supported by the POLICY CONTEXT. False if the summary invents, assumes, or "
        "misstates any coverage detail not present in the context."
    )
    rationale: str = Field(description="One sentence explaining the verdict.")


def load_judge_prompt(version: str) -> str:
    return (JUDGE_PROMPTS_DIR / f"judge_{version}.txt").read_text(encoding="utf-8")


def _build_context(chunks: list[RetrievedChunk]) -> str:
    blocks = [f"[{i}] source: {rc.chunk.source}\n{rc.chunk.text.strip()}" for i, rc in enumerate(chunks, start=1)]
    return "\n\n---\n\n".join(blocks)


def _build_judge_user_prompt(adjuster_notes: str, chunks: list[RetrievedChunk], summary: ClaimSummary) -> str:
    return (
        f"ADJUSTER NOTES:\n{adjuster_notes.strip()}\n\n"
        f"POLICY CONTEXT:\n{_build_context(chunks)}\n\n"
        f"CLAIM SUMMARY TO JUDGE:\n{summary.summary}\n"
        f"Coverage decision stated: {summary.coverage_decision}\n"
        f"Exclusion clause cited: {summary.exclusion_clause_id or 'none'}\n\n"
        "Judge this summary now."
    )


class Judge:
    def __init__(self, prompt_version: str, api_key: str | None = None, model: str | None = None):
        api_key = api_key or settings.gemini_api_key
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY is not set. Add it to your .env file.")
        self.model = model or settings.gemini_model
        self.prompt_version = prompt_version
        self.system_prompt = load_judge_prompt(prompt_version)
        self.client = instructor.from_genai(genai.Client(api_key=api_key))

    def judge(self, adjuster_notes: str, chunks: list[RetrievedChunk], summary: ClaimSummary) -> JudgeVerdict:
        verdict = self.client.chat.completions.create(
            model=self.model,
            response_model=JudgeVerdict,
            max_retries=settings.max_retries,
            messages=[
                {"role": "system", "content": self.system_prompt},
                {"role": "user", "content": _build_judge_user_prompt(adjuster_notes, chunks, summary)},
            ],
        )
        return verdict
