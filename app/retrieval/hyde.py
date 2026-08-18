from __future__ import annotations

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

_HYDE_PROMPT = (
    "You are an insurance document assistant. "
    "Write a short, factual passage (2-4 sentences) that would appear in an insurance policy document "
    "and directly answers the following question. "
    "Write only the passage — no preamble, no explanation.\n\nQuestion: {question}"
)


def hyde_embed(question: str) -> list[float]:
    """
    Hypothetical Document Embeddings — generate a hypothetical answer document,
    embed it, and use that vector for retrieval.

    The hypothetical document is closer to real document language than the raw
    question, so it lands nearer to the actual answer chunk in vector space.
    Falls back to embedding the original question if generation fails.
    """
    from app.embeddings.embedder import get_embedder

    embedder = get_embedder()

    try:
        from google import genai
        client = genai.Client(api_key=settings.gemini_api_key)
        response = client.models.generate_content(
            model=settings.gemini_model,
            contents=_HYDE_PROMPT.format(question=question),
        )
        hypothetical_doc = response.text.strip()
        if hypothetical_doc:
            logger.info("HyDE generated hypothetical doc: %r", hypothetical_doc[:80])
            return embedder.embed_documents([hypothetical_doc])[0]
    except Exception as exc:
        logger.warning("HyDE generation failed (%s) — falling back to query embedding.", exc)

    return embedder.embed_query(question)
