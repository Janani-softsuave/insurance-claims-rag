from __future__ import annotations

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

_REWRITE_PROMPT = (
    "Rewrite the following user question into a precise, keyword-rich search query "
    "for an insurance document retrieval system. "
    "Remove filler words, expand abbreviations, keep all important terms. "
    "Return ONLY the rewritten query — no explanation.\n\nQuestion: {question}"
)


def rewrite_query(question: str) -> str:
    try:
        from google import genai
        client = genai.Client(api_key=settings.gemini_api_key)
        response = client.models.generate_content(
            model=settings.gemini_model,
            contents=_REWRITE_PROMPT.format(question=question),
        )
        rewritten = response.text.strip()
        if rewritten:
            logger.info("Query rewritten: %r -> %r", question, rewritten)
            return rewritten
    except Exception as exc:
        logger.warning("Query rewriting failed (%s) — using original.", exc)
    return question
