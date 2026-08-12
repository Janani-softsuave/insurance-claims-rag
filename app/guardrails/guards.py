from __future__ import annotations

import re

from app.core.config import settings
from app.core.logging import get_logger
from app.models.schemas import RetrievedChunk

logger = get_logger(__name__)

_INJECTION_PATTERNS = [
    r"ignore (all |the )?(previous|above|prior) instructions",
    r"disregard (the |all )?(previous|above|system)",
    r"forget (everything|all|your instructions)",
    r"you are now",
    r"reveal (your )?(system )?prompt",
    r"act as (a |an )?(dan|jailbreak)",
]
_INJECTION_RE = re.compile("|".join(_INJECTION_PATTERNS), re.IGNORECASE)


class InputValidationError(ValueError):
    pass


def validate_question(question: str) -> str:
    if not question or not question.strip():
        raise InputValidationError("Question must not be empty.")
    cleaned = question.strip()
    if len(cleaned) > 1000:
        raise InputValidationError("Question is too long (max 1000 characters).")
    if _INJECTION_RE.search(cleaned):
        logger.warning("Prompt-injection attempt blocked: %r", cleaned)
        raise InputValidationError("This question was refused.")
    return cleaned


def is_grounded(chunks: list[RetrievedChunk], threshold: float | None = None) -> bool:
    threshold = settings.score_threshold if threshold is None else threshold
    if not chunks:
        return False
    best = max(c.score for c in chunks)
    if best < threshold:
        logger.info("Below grounding threshold (best=%.3f < %.3f) — refusing.", best, threshold)
        return False
    return True
