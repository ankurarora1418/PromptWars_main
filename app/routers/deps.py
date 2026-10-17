"""Shared route dependencies and the AI-answer helper used by every module."""

from typing import Any

from fastapi import Request

from app.config import Settings
from app.languages import offline_language
from app.schemas import AIAnswer
from app.services.ai_client import AIClient, ImageInput
from app.services.prompts import build_prompt


def get_ai(request: Request) -> AIClient:
    """The AI client stored on the app (overridable in tests)."""
    return request.app.state.ai


def get_app_settings(request: Request) -> Settings:
    return request.app.state.settings


async def ai_answer(
    ai: AIClient,
    *,
    task: str,
    language: str,
    offline_text: str,
    facts: dict[str, Any] | None = None,
    worker_input: str | None = None,
    image: ImageInput | None = None,
    privacy_note: str | None = None,
) -> AIAnswer:
    """Ask Gemini; if it is unavailable, return the deterministic ``offline_text``."""
    prompt = build_prompt(task, language, facts=facts, worker_input=worker_input)
    text = await ai.generate(prompt, language, image=image)
    if text:
        return AIAnswer(text=text, source="gemini", language=language, privacy_note=privacy_note)
    return AIAnswer(
        text=offline_text,
        source="offline",
        language=offline_language(language),
        privacy_note=privacy_note,
    )
