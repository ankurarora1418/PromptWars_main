"""Weekly income-goal planner.

Given the worker's weekly goal and the days they have logged, decide — in plain, tested code —
whether the goal is reachable *safely* before the week ends, how many hours it needs at their
own current rate, and which days and platform pay them best. Gemini never computes these
numbers; it only explains them.

Decision rules (see :func:`plan_week`):

* ``achieved``  — this week's take-home already meets the goal.
* ``week_over`` — the week has ended short of the goal; a new plan starts on Monday.
* ``no_data``   — no hourly rate is known yet, so hours cannot be estimated.
* ``unsafe``    — reaching the goal needs more than ``SAFE_DAY_HOURS`` a day or pushes the week
  past ``SAFE_WEEK_HOURS``; we suggest a realistic goal instead of encouraging overwork.
* ``stretch``   — reachable, but needs more than ``STRETCH_DAY_HOURS`` a day.
* ``on_track``  — reachable within a normal working day.
"""

from collections import defaultdict
from dataclasses import asdict, dataclass, field
from datetime import date, timedelta

from app.schemas import EarningEntry
from app.services.earnings import money, net_of, rate_per_hour

SAFE_DAY_HOURS = 12.0  # matches the long-shift alert in the earnings module
SAFE_WEEK_HOURS = 60.0  # rest-day guidance for road and manual work
STRETCH_DAY_HOURS = 10.0
MIN_WEEKDAY_SAMPLES = 2  # need at least this many weekdays before naming "best days"

WEEKDAYS = {
    "en": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"],
    "hi": ["सोमवार", "मंगलवार", "बुधवार", "गुरुवार", "शुक्रवार", "शनिवार", "रविवार"],
}


@dataclass
class WeeklyPlan:
    """Where the worker stands against this week's goal, and what to do next."""

    goal: float
    status: str  # achieved | on_track | stretch | unsafe | week_over | no_data
    week_start: str
    earned: float = 0.0
    remaining: float = 0.0
    progress: float = 0.0  # 0..1, for a progress bar
    hours_worked: float = 0.0
    days_left: int = 0
    rate_per_hour: float | None = None
    hours_needed: float | None = None
    hours_per_day: float | None = None
    realistic_goal: float | None = None
    best_weekdays: list[int] = field(default_factory=list)  # 0 = Monday
    best_platform: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


def _best_weekdays(entries: list[EarningEntry]) -> list[int]:
    """Up to two weekdays with the highest take-home per hour across all logged days."""
    by_weekday: dict[int, list[EarningEntry]] = defaultdict(list)
    for entry in entries:
        by_weekday[entry.day.weekday()].append(entry)
    rates = {day: rate for day, items in by_weekday.items() if (rate := rate_per_hour(items)) is not None}
    if len(rates) < MIN_WEEKDAY_SAMPLES:
        return []
    return sorted(rates, key=lambda day: (-rates[day], day))[:2]


def _best_platform(entries: list[EarningEntry]) -> str | None:
    by_platform: dict[str, list[EarningEntry]] = defaultdict(list)
    for entry in entries:
        by_platform[entry.platform].append(entry)
    rates = {name: rate for name, items in by_platform.items() if (rate := rate_per_hour(items)) is not None}
    if len(rates) < 2:
        return None
    return max(rates, key=lambda name: rates[name])


def plan_week(goal: float, entries: list[EarningEntry], today: date) -> WeeklyPlan:
    """Plan the rest of the current Monday-to-Sunday week towards ``goal`` rupees."""
    week_start = today - timedelta(days=today.weekday())
    this_week = [e for e in entries if week_start <= e.day <= today]
    worked_today = any(e.day == today for e in this_week)
    # Days still available to work, counting today only if nothing is logged for it yet.
    days_left = 6 - today.weekday() + (0 if worked_today else 1)

    plan = WeeklyPlan(goal=float(goal), status="no_data", week_start=week_start.isoformat())
    plan.earned = round(sum(net_of(e) for e in this_week), 2)
    plan.hours_worked = round(sum(e.hours for e in this_week), 2)
    plan.remaining = round(max(goal - plan.earned, 0.0), 2)
    plan.progress = round(min(plan.earned / goal, 1.0), 3) if goal > 0 else 1.0
    plan.days_left = days_left
    plan.best_weekdays = _best_weekdays(entries)
    plan.best_platform = _best_platform(entries)
    # Prefer this week's rate (most current); fall back to the whole history.
    plan.rate_per_hour = rate_per_hour(this_week) or rate_per_hour(entries)

    if plan.remaining <= 0:
        plan.status = "achieved"
        return plan
    if days_left == 0:
        plan.status = "week_over"
        return plan
    if not plan.rate_per_hour or plan.rate_per_hour <= 0:
        return plan  # status stays "no_data"

    plan.hours_needed = round(plan.remaining / plan.rate_per_hour, 1)
    plan.hours_per_day = round(plan.hours_needed / days_left, 1)
    safe_hours_left = min(days_left * SAFE_DAY_HOURS, max(SAFE_WEEK_HOURS - plan.hours_worked, 0.0))
    if plan.hours_needed > safe_hours_left:
        plan.status = "unsafe"
        plan.realistic_goal = round(plan.earned + safe_hours_left * plan.rate_per_hour, -1)
    elif plan.hours_per_day > STRETCH_DAY_HOURS:
        plan.status = "stretch"
    else:
        plan.status = "on_track"
    return plan


_TEXT = {
    "en": {
        "achieved": "Goal reached! You have earned {earned} this week against a goal of {goal}. Rest well.",
        "week_over": "This week you earned {earned} of your {goal} goal. A fresh plan starts on Monday.",
        "no_data": "Log at least one day with hours worked so Saathi can plan your {goal} weekly goal.",
        "on_track": "You need {remaining} more. At your rate of {rate}/hr that is about {hours} hours — around {per_day} hours a day for {days} days.",
        "stretch": "You need {remaining} more: about {per_day} hours a day for {days} days at {rate}/hr. That is a long stretch — plan breaks.",
        "unsafe": "Reaching {goal} would need more than safe working hours. A realistic goal this week is about {realistic}. Do not risk your health or safety for it.",
        "best_days": "You earn most per hour on {days}.",
        "best_platform": "{platform} pays you best per hour.",
    },
    "hi": {
        "achieved": "लक्ष्य पूरा! इस हफ्ते {goal} के लक्ष्य के मुकाबले आपने {earned} कमाए। अच्छे से आराम करें।",
        "week_over": "इस हफ्ते आपने {goal} के लक्ष्य में से {earned} कमाए। सोमवार से नई योजना शुरू होगी।",
        "no_data": "{goal} के साप्ताहिक लक्ष्य की योजना के लिए कम से कम एक दिन घंटों के साथ दर्ज करें।",
        "on_track": "आपको {remaining} और चाहिए। आपकी दर {rate}/घंटा पर यह लगभग {hours} घंटे है — {days} दिन तक रोज़ करीब {per_day} घंटे।",
        "stretch": "आपको {remaining} और चाहिए: {rate}/घंटा पर {days} दिन तक रोज़ लगभग {per_day} घंटे। यह लंबा है — बीच में आराम की योजना बनाएँ।",
        "unsafe": "{goal} तक पहुँचने में सुरक्षित घंटों से ज़्यादा काम करना पड़ेगा। इस हफ्ते सही लक्ष्य लगभग {realistic} है। इसके लिए सेहत या सुरक्षा जोखिम में न डालें।",
        "best_days": "आपको {days} को प्रति घंटा सबसे ज़्यादा मिलता है।",
        "best_platform": "{platform} पर प्रति घंटा सबसे अच्छी कमाई है।",
    },
}


def _hours(value: float | None) -> str:
    """``40.0`` -> ``"40"``, ``10.8`` -> ``"10.8"``."""
    return "—" if value is None else f"{value:g}"


def plan_message(plan: WeeklyPlan, lang: str) -> str:
    """One or two plain sentences describing the plan in English or Hindi."""
    text = _TEXT.get(lang, _TEXT["en"])
    lines = [
        text[plan.status].format(
            goal=money(plan.goal),
            earned=money(plan.earned),
            remaining=money(plan.remaining),
            rate=money(plan.rate_per_hour),
            hours=_hours(plan.hours_needed),
            per_day=_hours(plan.hours_per_day),
            days=plan.days_left,
            realistic=money(plan.realistic_goal),
        )
    ]
    if plan.status in {"on_track", "stretch", "unsafe"}:
        if plan.best_weekdays:
            names = WEEKDAYS.get(lang, WEEKDAYS["en"])
            joiner = " और " if lang == "hi" else " and "
            lines.append(text["best_days"].format(days=joiner.join(names[d] for d in plan.best_weekdays)))
        if plan.best_platform:
            lines.append(text["best_platform"].format(platform=plan.best_platform))
    return " ".join(lines)
