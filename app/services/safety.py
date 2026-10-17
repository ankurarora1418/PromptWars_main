"""Context-aware safety tip selection."""

from dataclasses import dataclass

from app.languages import offline_language
from app.schemas import Profile
from app.services import knowledge

NIGHT_HOURS = set(range(20, 24)) | set(range(0, 6))


@dataclass
class SafetyTip:
    id: str
    text: str
    score: int


def situation(profile: Profile, hour: int, conditions: list[str], long_hours: bool = False) -> set[str]:
    """Translate the worker's context into situation tags used by the tip rules."""
    tags = set(conditions)
    if hour in NIGHT_HOURS or profile.shift == "night":
        tags.add("night")
    if long_hours:
        tags.add("long_hours")
    return tags


def select_tips(
    profile: Profile,
    hour: int,
    conditions: list[str],
    long_hours: bool = False,
    limit: int = 4,
) -> list[SafetyTip]:
    """Pick the most relevant tips for this worker right now.

    A tip qualifies if it fits the work type (or applies to everyone) and, when it is tied to a
    situation (night, heat, rain...), that situation is active. Situation matches score higher,
    so urgent, context-specific advice comes first.
    """
    lang = offline_language(profile.language)
    tags = situation(profile, hour, conditions, long_hours)
    picked: list[SafetyTip] = []
    for tip in knowledge.safety_tips():
        if tip["work_types"] and profile.work_type not in tip["work_types"]:
            continue
        when = set(tip["when"])
        if when and not (when & tags):
            continue
        score = tip["priority"] + (5 if when else 0)
        picked.append(SafetyTip(id=tip["id"], text=knowledge.localized(tip["text"], lang), score=score))
    picked.sort(key=lambda t: (-t.score, t.id))
    return picked[:limit]
