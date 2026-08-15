"""Central Groq API client.

Wraps the Groq SDK to provide:
  * chat completion with retries + model fallback
  * JSON-mode structured outputs (classification / extraction)
  * vision-capable completions (OCR on image content)

All providers in the pipeline call through this client so the Groq key
is used in one place only.

Resilience behaviour (the reason the pipeline used to crawl):
  * permanent API errors (decommissioned / unknown model, invalid request)
    are NOT retried — the model is marked dead and the next candidate is
    tried immediately, so a misconfigured model never costs retry sleeps;
  * transient errors (429 rate limit, 5xx, network) are retried a bounded
    number of times with backoff that honours ``Retry-After``;
  * after a 429 the client enters a rate-limit cooldown and every further
    call fails instantly, so classification / extraction / OCR / summary
    fall back to the deterministic rules layer instead of hammering the API.
"""
from __future__ import annotations

import json
import time
from typing import Any

from app.config import settings
from app.core.logging import get_logger

logger = get_logger("ai.groq")

try:
    from groq import AsyncGroq
    from groq.types.chat import ChatCompletion  # noqa: F401
except ImportError:  # pragma: no cover
    AsyncGroq = None

_vision_available_cache: bool | None = None

# Permanent error codes: retrying these is pure waste.
_PERMANENT_CODES = {
    "invalid_request_error",
    "model_not_found",
    "model_decommissioned",
    "authentication_error",
    "permission_denied",
    "invalid_api_key",
    "insufficient_quota",
    "invalid_messages",
    "bad_request_error",
}


def _error_code(exc: Exception) -> str | None:
    """Best-effort extraction of the Groq ``error.code`` string."""
    body = getattr(exc, "body", None)
    if isinstance(body, dict):
        err = body.get("error") or {}
        return err.get("code")
    message = str(exc)
    for marker in ('"code": "', "'code': '"):
        idx = message.find(marker)
        if idx != -1:
            return message[idx + len(marker):].split('"', 1)[0]
    return None


def _retry_after(exc: Exception) -> float | None:
    """Seconds to wait before retrying, from the Retry-After header."""
    if getattr(exc, "status_code", None) != 429:
        return None
    headers = getattr(exc, "headers", None) or {}
    value = headers.get("Retry-After") or headers.get("retry-after")
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


class GroqClient:
    def __init__(self) -> None:
        self.available = settings.groq_available and AsyncGroq is not None
        self._client: AsyncGroq | None = None
        self._dead_models: set[str] = set()
        # Cooldown window (monotonic seconds) after a 429; None = not limited.
        self._rate_limit_until: float | None = None
        if self.available:
            self._client = AsyncGroq(api_key=settings.GROQ_API_KEY)

    @property
    def client(self) -> AsyncGroq:
        if not self.available:
            raise RuntimeError("Groq API key not configured. Set GROQ_API_KEY in backend/.env")
        return self._client  # type: ignore[return-value]

    # --- Configuration helpers --------------------------------------------------

    def has_vision_config(self) -> bool:
        """True when a Groq vision model is actually configured."""
        return bool(settings.GROQ_VISION_MODEL.strip() or settings.GROQ_VISION_MODELS)

    def text_candidates(self, primary: str | None) -> list[str]:
        """Ordered text models for a completion, deduplicated."""
        candidates = [primary or settings.GROQ_MODEL]
        for model in settings.GROQ_FALLBACK_MODELS:
            if model not in candidates:
                candidates.append(model)
        return candidates

    def vision_candidates(self) -> list[str]:
        """Ordered vision models for OCR, deduplicated."""
        candidates = []
        if settings.GROQ_VISION_MODEL.strip():
            candidates.append(settings.GROQ_VISION_MODEL)
        for model in settings.GROQ_VISION_MODELS:
            if model not in candidates:
                candidates.append(model)
        return candidates

    def in_rate_limit_cooldown(self) -> bool:
        if self._rate_limit_until is None:
            return False
        if time.monotonic() >= self._rate_limit_until:
            self._rate_limit_until = None
            return False
        return True

    # --- Model discovery ----------------------------------------------------------

    async def list_models(self) -> list[str]:
        """List model IDs available on the configured account."""
        try:
            resp = await self.client.models.list()
            return [m.id for m in resp.data]
        except Exception as exc:  # noqa: BLE001
            logger.warning("Could not list Groq models: %s", exc)
            return []

    async def vision_available(self) -> bool:
        """True when at least one configured vision model exists on this account."""
        global _vision_available_cache  # noqa: PLW0603
        if _vision_available_cache is not None:
            return _vision_available_cache
        available = False
        if self.available:
            candidates = self.vision_candidates()
            if candidates:
                ids = set(await self.list_models())
                available = any(m in ids for m in candidates)
        _vision_available_cache = available
        if not available:
            logger.warning("No Groq vision model is available on this account — vision OCR will be skipped")
        return available

    # --- Completion core ------------------------------------------------------------

    async def _complete(
        self,
        messages: list[dict[str, Any]],
        candidates: list[str] | None = None,
        max_tokens: int = 3000,
        temperature: float = 0.1,
        json_mode: bool = False,
        is_vision: bool = False,
    ) -> dict[str, Any]:
        """Run a completion with retries + model fallback (text or vision).

        Permanent errors skip to the next candidate immediately; transient
        errors retry the same candidate with backoff. While the org is inside
        its 429 cooldown window every call raises instantly.
        """
        if not self.available:
            raise RuntimeError("Groq API key not configured. Set GROQ_API_KEY in backend/.env")
        if self.in_rate_limit_cooldown():
            raise RuntimeError(
                "Groq rate limit cooldown active — skipping LLM call to keep the pipeline fast"
            )
        if candidates is None:
            candidates = self.vision_candidates() if is_vision else self.text_candidates(settings.GROQ_MODEL)
        candidates = [m for m in candidates if m not in self._dead_models]
        if not candidates:
            raise RuntimeError("No usable Groq model configured")

        transient_seen = False
        last_error: Exception | None = None
        for candidate in candidates:
            for attempt in range(settings.GROQ_MAX_RETRIES + 1):
                try:
                    kwargs: dict[str, Any] = {
                        "model": candidate,
                        "messages": messages,
                        "max_tokens": max_tokens,
                        "temperature": temperature,
                    }
                    if json_mode:
                        kwargs["response_format"] = {"type": "json_object"}
                    resp = await self.client.chat.completions.create(**kwargs)
                    content = resp.choices[0].message.content or ""
                    return {"content": content, "model": candidate, "usage": resp.usage}
                except Exception as exc:  # noqa: BLE001
                    last_error = exc
                    code = _error_code(exc)
                    status = getattr(exc, "status_code", None)
                    if code in _PERMANENT_CODES or (isinstance(status, int) and 400 <= status < 500):
                        # Permanent: never retry this model again in this process.
                        self._dead_models.add(candidate)
                        logger.warning("Groq model %s unavailable (%s): %s", candidate, code or status, exc)
                        break
                    # Transient (429 / 5xx / network): back off and retry.
                    transient_seen = True
                    if status == 429:
                        wait = _retry_after(exc) or settings.GROQ_RATE_LIMIT_COOLDOWN_SECONDS
                        self._rate_limit_until = time.monotonic() + wait
                        logger.warning(
                            "Groq rate limited on %s — failing fast for %.0fs", candidate, wait
                        )
                        raise RuntimeError(
                            f"Groq rate limited (org TPD reached): retry in {wait:.0f}s"
                        ) from exc
                    wait = min(1.5 * (attempt + 1), 4.0)
                    logger.warning(
                        "Groq call failed on %s (attempt %d): %s", candidate, attempt + 1, exc
                    )
                    time.sleep(wait)

        if transient_seen:
            raise RuntimeError(f"Groq request failed after retries: {last_error}")
        raise RuntimeError(
            f"All configured Groq models are unavailable: {last_error or 'no candidates'}"
        )

    # --- Public API ---------------------------------------------------------------

    async def complete(
        self,
        system: str,
        user: str,
        json_mode: bool = False,
        max_tokens: int = 3000,
    ) -> dict[str, Any]:
        return await self._complete(
            [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            json_mode=json_mode,
            max_tokens=max_tokens,
        )

    async def complete_json(self, system: str, user: str, max_tokens: int = 3000) -> dict[str, Any]:
        return await self.complete(system, user, json_mode=True, max_tokens=max_tokens)

    async def vision_ocr(
        self,
        image_b64: str,
        instructions: str,
        max_tokens: int = 2500,
    ) -> dict[str, Any]:
        """OCR / transcribe an image using a Groq vision model."""
        if not self.has_vision_config():
            raise RuntimeError("No Groq vision model is configured on this account")
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": instructions},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"},
                    },
                ],
            }
        ]
        return await self._complete(messages, is_vision=True, max_tokens=max_tokens)

    def parse_json(self, content: str) -> dict[str, Any]:
        """Best-effort parse of a JSON object from an LLM response."""
        content = content.strip()
        if content.startswith("```"):
            content = content.strip("`")
            if content.startswith("json"):
                content = content[4:]
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            start = content.find("{")
            end = content.rfind("}")
            if start != -1 and end > start:
                return json.loads(content[start : end + 1])
            raise


groq_client = GroqClient()
