from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from time import perf_counter

import instructor
from google import genai

from app.core.config import settings
from app.core.logging import get_logger
from app.generation.prompts import PROMPT_VERSION, SYSTEM_PROMPT, build_user_prompt
from app.models.schemas import GroundedAnswer, RetrievedChunk

logger = get_logger(__name__)


@dataclass
class GenerationTrace:
    answer: GroundedAnswer
    prompt_version: str
    model: str
    generation_params: dict = field(default_factory=dict)
    raw_output: str | None = None
    raw_output_note: str | None = None
    latency_ms: int = 0


class Generator:
    def __init__(self, api_key: str | None = None, model: str | None = None):
        api_key = api_key or settings.gemini_api_key
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY is not set. Add it to your .env file.")
        self.model = model or settings.gemini_model
        self.client = instructor.from_genai(genai.Client(api_key=api_key))

    def generate(self, question: str, chunks: list[RetrievedChunk]) -> GenerationTrace:
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": build_user_prompt(question, chunks)},
        ]
        generation_params = {"max_retries": settings.max_retries}
        started = perf_counter()

        raw_output: str | None = None
        raw_output_note: str | None = None
        try:
            answer, completion = self.client.chat.completions.create_with_completion(
                model=self.model,
                response_model=GroundedAnswer,
                max_retries=settings.max_retries,
                messages=messages,
            )
            raw_output = str(completion)
        except AttributeError:
            answer = self.client.chat.completions.create(
                model=self.model,
                response_model=GroundedAnswer,
                max_retries=settings.max_retries,
                messages=messages,
            )
            raw_output_note = (
                "instructor's genai adapter does not expose create_with_completion here — "
                "the raw provider payload could not be captured, so the parsed structured "
                "answer is stored in its place."
            )

        latency_ms = int((perf_counter() - started) * 1000)
        logger.info("Generated answer (can_answer=%s, %d citation(s))", answer.can_answer, len(answer.citations))
        return GenerationTrace(
            answer=answer,
            prompt_version=PROMPT_VERSION,
            model=self.model,
            generation_params=generation_params,
            raw_output=raw_output,
            raw_output_note=raw_output_note,
            latency_ms=latency_ms,
        )


@lru_cache
def get_generator() -> Generator:
    return Generator()
