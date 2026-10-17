"""Gemini client with timeout, caching and graceful offline fallback.

Every feature calls :meth:`AIClient.generate`. If Gemini is not configured, times out, or
errors, it returns ``None`` and the caller uses its deterministic template instead, so one
failing API call never breaks a user flow.
"""

import asyncio
import hashlib
import logging
import time
from collections import OrderedDict
from dataclasses import dataclass
from typing import Protocol

from app.config import Settings
from app.services.prompts import system_instruction

logger = logging.getLogger("saathi.ai")


@dataclass(frozen=True)
class ImageInput:
    """An image to send alongside the prompt (already validated)."""

    data: bytes
    mime_type: str


class AIClient(Protocol):
    """Anything that can turn a prompt into text. Tests use a fake implementation."""

    @property
    def enabled(self) -> bool: ...

    async def generate(self, prompt: str, language: str, image: ImageInput | None = None) -> str | None: ...


class TTLCache:
    """Small in-memory LRU cache with expiry, for repeated identical prompts."""

    def __init__(self, max_size: int, ttl_seconds: int) -> None:
        self._max_size = max_size
        self._ttl = ttl_seconds
        self._items: OrderedDict[str, tuple[float, str]] = OrderedDict()

    def get(self, key: str) -> str | None:
        item = self._items.get(key)
        if item is None:
            return None
        stored_at, value = item
        if time.monotonic() - stored_at > self._ttl:
            del self._items[key]
            return None
        self._items.move_to_end(key)
        return value

    def set(self, key: str, value: str) -> None:
        if self._max_size <= 0:
            return
        self._items[key] = (time.monotonic(), value)
        self._items.move_to_end(key)
        while len(self._items) > self._max_size:
            self._items.popitem(last=False)

    def __len__(self) -> int:
        return len(self._items)


class GeminiClient:
    """Production client backed by the ``google-genai`` SDK."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._cache = TTLCache(settings.ai_cache_size, settings.ai_cache_ttl_seconds)
        self._client = None
        if settings.ai_enabled:
            from google import genai  # imported lazily so tests never need network setup

            self._client = genai.Client(api_key=settings.gemini_api_key.get_secret_value())

    @property
    def enabled(self) -> bool:
        return self._client is not None

    def _config(self, language: str):
        from google.genai import types

        config: dict = {
            "system_instruction": system_instruction(language),
            "temperature": 0.4,
            "max_output_tokens": self._settings.ai_max_output_tokens,
        }
        level = self._settings.gemini_thinking_level.strip().upper()
        if level:
            config["thinking_config"] = types.ThinkingConfig(thinking_level=level)
        return types.GenerateContentConfig(**config)

    async def generate(self, prompt: str, language: str, image: ImageInput | None = None) -> str | None:
        """Return model text, or ``None`` so the caller falls back to its template."""
        if not self.enabled:
            return None

        cache_key = None
        if image is None:  # images are never cached: they may hold personal data
            raw = f"{self._settings.gemini_model}|{language}|{prompt}"
            cache_key = hashlib.sha256(raw.encode("utf-8")).hexdigest()
            cached = self._cache.get(cache_key)
            if cached is not None:
                return cached

        from google.genai import types

        contents: list = [prompt]
        if image is not None:
            contents.insert(0, types.Part.from_bytes(data=image.data, mime_type=image.mime_type))

        try:
            response = await asyncio.wait_for(
                self._client.aio.models.generate_content(
                    model=self._settings.gemini_model,
                    contents=contents,
                    config=self._config(language),
                ),
                timeout=self._settings.ai_timeout_seconds,
            )
            text = (response.text or "").strip()
        except TimeoutError:
            logger.warning("Gemini timed out; using offline fallback")
            return None
        except Exception as exc:  # any SDK/network error -> graceful fallback
            logger.warning("Gemini call failed (%s); using offline fallback", type(exc).__name__)
            return None

        if not text:
            return None
        if cache_key:
            self._cache.set(cache_key, text)
        return text
