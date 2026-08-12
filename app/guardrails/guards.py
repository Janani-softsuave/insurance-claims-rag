"""Guardrails — input validation, prompt-injection screening, grounding check.

Carries forward Week-2's "catch bad input and refuse safely" idea, plus the
Week-3 grounding rule: if retrieval isn't confident enough, we refuse to answer
rather than let the model guess.
"""
from __future__ import annotations

import re

from app.core.config import settings
from app.core.logging import get_logger
from app.models.schemas import RetrievedChunk

logger = get_logger(__name__)

# Crude but useful signals that a user is trying to override the system prompt.
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
    """Raised when a user question fails validation."""


def validate_question(question: str) -> str:
    """Validate and normalize a user question. Raises on bad input."""
    if question is None:
        raise InputValidationError("Question is required.")
    cleaned = question.strip()
    if not cleaned:
        raise InputValidationError("Question must not be empty.")
    if len(cleaned) > 1000:
        raise InputValidationError("Question is too long (max 1000 characters).")
    if _INJECTION_RE.search(cleaned):
        # We don't crash — we flag it. The grounded prompt also defends against this,
        # but refusing early is cheaper and clearer.
        logger.warning("Possible prompt-injection attempt blocked: %r", cleaned)
        raise InputValidationError(
            "This question looks like an attempt to change the assistant's instructions "
            "and was refused."
        )
    return cleaned


def is_grounded(chunks: list[RetrievedChunk], threshold: float | None = None) -> bool:
    """True if the best reranked chunk clears the confidence threshold.

    When False, the service returns "I don't know" instead of generating —
    this is what makes the app admit ignorance on out-of-corpus questions.
    """
    threshold = settings.score_threshold if threshold is None else threshold
    if not chunks:
        return False
    best = max(c.score for c in chunks)
    grounded = best >= threshold
    if not grounded:
        logger.info("Below grounding threshold (best=%.3f < %.3f) — refusing.", best, threshold)
    return grounded
