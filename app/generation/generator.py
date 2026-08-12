"""Grounded generation with Gemini + structured output.

Uses `instructor` (Week-2) on top of the Gemini client so the model is forced to
return a validated `GroundedAnswer` — with automatic retry on validation
failure. That guarantees our program always gets `{can_answer, answer,
citations}` back, never free text it can't parse.
"""
from __future__ import annotations

from functools import lru_cache

import instructor
from google import genai

from app.core.config import settings
from app.core.logging import get_logger
from app.generation.prompts import SYSTEM_PROMPT, build_user_prompt
from app.models.schemas import GroundedAnswer, RetrievedChunk

logger = get_logger(__name__)


class Generator:
    def __init__(self, api_key: str | None = None, model: str | None = None):
        api_key = api_key or settings.gemini_api_key
        if not api_key:
            raise RuntimeError(
                "GEMINI_API_KEY is not set. Copy .env.example to .env and add your key."
            )
        self.model = model or settings.gemini_model
        # instructor wraps the Gemini client and enforces the response schema.
        self.client = instructor.from_genai(genai.Client(api_key=api_key))

    def generate(self, question: str, chunks: list[RetrievedChunk]) -> GroundedAnswer:
        """Produce a grounded, cited answer from the retrieved chunks."""
        user_prompt = build_user_prompt(question, chunks)
        answer = self.client.chat.completions.create(
            model=self.model,
            response_model=GroundedAnswer,
            max_retries=settings.max_retries,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
        )
        logger.info(
            "Generated answer (can_answer=%s, %d citation(s))",
            answer.can_answer,
            len(answer.citations),
        )
        return answer


@lru_cache
def get_generator() -> Generator:
    return Generator()
