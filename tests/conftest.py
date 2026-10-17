"""Shared test fixtures. Tests never call the real Gemini API."""

from datetime import date, timedelta

import pytest

from app.schemas import EarningEntry, Profile
from app.services.ai_client import ImageInput


class FakeAI:
    """Deterministic stand-in for Gemini that records every prompt it receives."""

    def __init__(self, reply: str | None = "AI reply", enabled: bool = True) -> None:
        self.reply = reply
        self._enabled = enabled
        self.prompts: list[str] = []
        self.images: list[ImageInput | None] = []

    @property
    def enabled(self) -> bool:
        return self._enabled

    async def generate(self, prompt: str, language: str, image: ImageInput | None = None):
        self.prompts.append(prompt)
        self.images.append(image)
        return self.reply if self._enabled else None


@pytest.fixture
def profile() -> Profile:
    return Profile(
        language="en", work_type="delivery", state="Punjab", age=28, monthly_income=14000, shift="day"
    )


def make_entries(per_hour_last_week: float, per_hour_this_week: float, today: date) -> list[EarningEntry]:
    """Seven days last week and seven days this week, 8 hours each, no costs."""
    entries = []
    for offset in range(14):
        day = today - timedelta(days=offset)
        rate = per_hour_this_week if offset <= 6 else per_hour_last_week
        entries.append(EarningEntry(day=day, platform="Swiggy", gross=rate * 8, hours=8))
    return entries
