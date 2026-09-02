from __future__ import annotations

from functools import lru_cache

import instructor
from google import genai

from app.core.config import settings
from app.core.logging import get_logger
from app.generation.claim_summary_prompts import (
    CLAIM_SUMMARY_SYSTEM_PROMPT,
    build_claim_summary_user_prompt,
)
from app.models.schemas import ClaimSummary, RetrievedChunk

logger = get_logger(__name__)


class ClaimSummarizer:
    def __init__(self, api_key: str | None = None, model: str | None = None):
        api_key = api_key or settings.gemini_api_key
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY is not set. Add it to your .env file.")
        self.model = model or settings.gemini_model
        self.client = instructor.from_genai(genai.Client(api_key=api_key))

    def summarize(self, adjuster_notes: str, chunks: list[RetrievedChunk]) -> ClaimSummary:
        summary = self.client.chat.completions.create(
            model=self.model,
            response_model=ClaimSummary,
            max_retries=settings.max_retries,
            messages=[
                {"role": "system", "content": CLAIM_SUMMARY_SYSTEM_PROMPT},
                {"role": "user", "content": build_claim_summary_user_prompt(adjuster_notes, chunks)},
            ],
        )
        logger.info(
            "Generated claim summary (claim=%s, decision=%s)", summary.claim_number, summary.coverage_decision
        )
        return summary


@lru_cache
def get_claim_summarizer() -> ClaimSummarizer:
    return ClaimSummarizer()
