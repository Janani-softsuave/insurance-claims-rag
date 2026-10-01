from __future__ import annotations

import time

from google import genai
from google.genai import errors as genai_errors

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

ALL_KEYS_WAIT_SECONDS = 3600.0


def _retry_delay_seconds(exc: genai_errors.ClientError) -> float | None:
    details = exc.details if isinstance(exc.details, dict) else {}
    for item in details.get("details", []) or []:
        if item.get("@type", "").endswith("RetryInfo"):
            raw = item.get("retryDelay", "")
            if raw.endswith("s"):
                try:
                    return float(raw[:-1])
                except ValueError:
                    return None
    return None


class GeminiKeyRotatingClient:
    def __init__(self, api_key: str | None = None, model: str | None = None):
        self._key_pool = [api_key] if api_key else settings.gemini_api_key_pool()
        if not self._key_pool:
            self._key_pool = [""]
        self._key_index = 0
        self.model = model or settings.gemini_model
        self.client = genai.Client(api_key=self._key_pool[self._key_index])

    def generate(self, contents, config):
        same_key_retries = 0
        max_same_key_retries = 6
        server_error_retries = 0
        max_server_error_retries = 5
        server_error_cycle = 0
        cycle = 0
        while True:
            try:
                return self.client.models.generate_content(model=self.model, contents=contents, config=config)
            except genai_errors.ServerError as exc:
                if server_error_retries < max_server_error_retries:
                    server_error_retries += 1
                    delay = min(30, 5 * server_error_retries)
                    logger.warning(
                        "Gemini returned %s (server-side); backing off %.1fs (attempt %d/%d)",
                        exc.code, delay, server_error_retries, max_server_error_retries,
                    )
                    time.sleep(delay)
                    continue

                server_error_cycle += 1
                logger.warning(
                    "Gemini still returning %s after %d attempts (cycle %d) — sleeping %.0fs then retrying.",
                    exc.code, max_server_error_retries, server_error_cycle, ALL_KEYS_WAIT_SECONDS,
                )
                time.sleep(ALL_KEYS_WAIT_SECONDS)
                server_error_retries = 0
            except genai_errors.ClientError as exc:
                is_quota_error = exc.code == 429 or (exc.status or "").upper() == "RESOURCE_EXHAUSTED"
                if not is_quota_error:
                    raise

                if same_key_retries < max_same_key_retries:
                    same_key_retries += 1
                    delay = _retry_delay_seconds(exc) or min(60, 2 * (2**same_key_retries))
                    logger.warning(
                        "Gemini key %d/%d rate-limited (429); backing off %.1fs (attempt %d/%d)",
                        self._key_index + 1, len(self._key_pool), delay, same_key_retries, max_same_key_retries,
                    )
                    time.sleep(delay)
                    continue

                if self._key_index + 1 < len(self._key_pool):
                    self._key_index += 1
                    same_key_retries = 0
                    logger.warning(
                        "Gemini key %d/%d still rate-limited, rotating to key %d/%d",
                        self._key_index, len(self._key_pool), self._key_index + 1, len(self._key_pool),
                    )
                    self.client = genai.Client(api_key=self._key_pool[self._key_index])
                    continue

                cycle += 1
                logger.warning(
                    "All %d Gemini key(s) rate-limited (cycle %d) — sleeping %.0fs then retrying all keys.",
                    len(self._key_pool), cycle, ALL_KEYS_WAIT_SECONDS,
                )
                time.sleep(ALL_KEYS_WAIT_SECONDS)
                self._key_index = 0
                same_key_retries = 0
                self.client = genai.Client(api_key=self._key_pool[self._key_index])
