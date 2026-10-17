"""Deterministic earnings maths and anomaly detection.

Numbers are computed here, never by the LLM, so they are always correct. Gemini only explains
the resulting summary in the worker's language.
"""

from collections import defaultdict
from dataclasses import asdict, dataclass, field
from datetime import date, timedelta

from app.schemas import EarningEntry

PAY_DROP_THRESHOLD = 0.25  # 25% fall in hourly pay week-on-week triggers a warning
HIGH_DEDUCTION_SHARE = 0.20  # platform keeping >20% of gross is flagged
HIGH_EXPENSE_SHARE = 0.35  # fuel + other costs eating >35% of gross is flagged
LONG_DAY_HOURS = 12


@dataclass
class Alert:
    """Something the worker should act on. ``action`` links to another app module."""

    code: str
    severity: str  # "info" | "warning"
    action: str | None = None  # e.g. "grievance:wrong_deduction"
    data: dict = field(default_factory=dict)


@dataclass
class EarningsSummary:
    days_worked: int = 0
    total_gross: float = 0.0
    total_tips: float = 0.0
    total_deductions: float = 0.0
    total_expenses: float = 0.0
    net_earnings: float = 0.0
    total_hours: float = 0.0
    total_km: float = 0.0
    net_per_hour: float | None = None
    net_per_km: float | None = None
    expense_share: float | None = None
    deduction_share: float | None = None
    best_platform: str | None = None
    by_platform: dict[str, dict[str, float]] = field(default_factory=dict)
    daily: list[dict] = field(default_factory=list)
    this_week_per_hour: float | None = None
    last_week_per_hour: float | None = None
    alerts: list[Alert] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def _round(value: float) -> float:
    return round(value, 2)


def money(value: float | None) -> str:
    """Format rupees for people: ₹10,510 rather than 10510.0."""
    return "—" if value is None else f"₹{value:,.0f}"


def net_of(entry: EarningEntry) -> float:
    """Take-home for one entry: pay + tips - platform cuts - fuel - other costs."""
    """Take-home for one entry: pay + tips - platform cuts - fuel - other costs."""
    return entry.gross + entry.tips - entry.platform_deductions - entry.fuel_cost - entry.other_expenses


def rate_per_hour(entries: list[EarningEntry]) -> float | None:
    """Take-home per hour worked, or ``None`` when no hours are logged."""
    hours = sum(e.hours for e in entries)
    if hours <= 0:
        return None
    return _round(sum(net_of(e) for e in entries) / hours)


def summarize(entries: list[EarningEntry], today: date | None = None) -> EarningsSummary:
    """Compute totals, rates, per-platform breakdown, weekly trend and alerts."""
    summary = EarningsSummary()
    if not entries:
        return summary

    today = today or max(e.day for e in entries)
    summary.days_worked = len({e.day for e in entries})
    summary.total_gross = _round(sum(e.gross for e in entries))
    summary.total_tips = _round(sum(e.tips for e in entries))
    summary.total_deductions = _round(sum(e.platform_deductions for e in entries))
    summary.total_expenses = _round(sum(e.fuel_cost + e.other_expenses for e in entries))
    summary.net_earnings = _round(sum(net_of(e) for e in entries))
    summary.total_hours = _round(sum(e.hours for e in entries))
    summary.total_km = _round(sum(e.km for e in entries))
    summary.net_per_hour = rate_per_hour(entries)
    if summary.total_km > 0:
        summary.net_per_km = _round(summary.net_earnings / summary.total_km)
    earned = summary.total_gross + summary.total_tips
    if earned > 0:
        summary.expense_share = _round(summary.total_expenses / earned)
        summary.deduction_share = _round(summary.total_deductions / earned)

    platforms: dict[str, list[EarningEntry]] = defaultdict(list)
    for entry in entries:
        platforms[entry.platform].append(entry)
    for name, items in sorted(platforms.items()):
        summary.by_platform[name] = {
            "net": _round(sum(net_of(e) for e in items)),
            "hours": _round(sum(e.hours for e in items)),
            "net_per_hour": rate_per_hour(items) or 0.0,
        }
    if len(summary.by_platform) > 1:
        summary.best_platform = max(summary.by_platform, key=lambda p: summary.by_platform[p]["net_per_hour"])

    by_day: dict[date, float] = defaultdict(float)
    for entry in entries:
        by_day[entry.day] += net_of(entry)
    summary.daily = [{"day": d.isoformat(), "net": _round(v)} for d, v in sorted(by_day.items())]

    week_start = today - timedelta(days=6)
    prev_start = week_start - timedelta(days=7)
    this_week = [e for e in entries if week_start <= e.day <= today]
    last_week = [e for e in entries if prev_start <= e.day < week_start]
    summary.this_week_per_hour = rate_per_hour(this_week)
    summary.last_week_per_hour = rate_per_hour(last_week)

    summary.alerts = _alerts(summary, entries)
    return summary


def _alerts(summary: EarningsSummary, entries: list[EarningEntry]) -> list[Alert]:
    alerts: list[Alert] = []
    now, before = summary.this_week_per_hour, summary.last_week_per_hour
    if now is not None and before and before > 0 and (before - now) / before >= PAY_DROP_THRESHOLD:
        alerts.append(
            Alert(
                code="pay_drop",
                severity="warning",
                action="grievance:incentive_not_paid",
                data={
                    "this_week": now,
                    "last_week": before,
                    "drop_pct": round((before - now) / before * 100),
                },
            )
        )
    if summary.deduction_share is not None and summary.deduction_share > HIGH_DEDUCTION_SHARE:
        alerts.append(
            Alert(
                code="high_deductions",
                severity="warning",
                action="grievance:wrong_deduction",
                data={"share_pct": round(summary.deduction_share * 100), "amount": summary.total_deductions},
            )
        )
    if summary.expense_share is not None and summary.expense_share > HIGH_EXPENSE_SHARE:
        alerts.append(
            Alert(
                code="high_expenses",
                severity="info",
                data={"share_pct": round(summary.expense_share * 100)},
            )
        )
    long_days = sorted({e.day.isoformat() for e in entries if e.hours >= LONG_DAY_HOURS})
    if long_days:
        alerts.append(
            Alert(code="long_hours", severity="info", action="safety", data={"days": long_days[-3:]})
        )
    if summary.best_platform:
        alerts.append(Alert(code="best_platform", severity="info", data={"platform": summary.best_platform}))
    return alerts


_ALERT_TEXT = {
    "en": {
        "pay_drop": "Your earnings per hour fell {drop_pct}% this week ({this_week}/hr vs {last_week}/hr). If an incentive or payout is missing, raise a complaint.",
        "high_deductions": "The platform kept {share_pct}% of your earnings ({amount}). Check each deduction; you can dispute wrong ones.",
        "high_expenses": "Fuel and other costs take {share_pct}% of your earnings. Planning routes and servicing your vehicle can cut this.",
        "long_hours": "You worked 12+ hours on {days}. Long shifts raise accident risk — take breaks and drink water.",
        "best_platform": "{platform} pays you the most per hour. Prefer it when you can choose.",
    },
    "hi": {
        "pay_drop": "इस हफ्ते आपकी प्रति घंटा कमाई {drop_pct}% घटी ({this_week}/घंटा, पिछले हफ्ते {last_week}/घंटा)। अगर कोई इंसेंटिव या भुगतान नहीं मिला है, तो शिकायत दर्ज करें।",
        "high_deductions": "प्लेटफॉर्म ने आपकी कमाई का {share_pct}% ({amount}) काटा। हर कटौती जाँचें; गलत कटौती पर आपत्ति कर सकते हैं।",
        "high_expenses": "ईंधन और दूसरे खर्च आपकी कमाई का {share_pct}% ले रहे हैं। सही रास्ता चुनकर और गाड़ी की सर्विस करवाकर यह कम हो सकता है।",
        "long_hours": "आपने {days} को 12+ घंटे काम किया। लंबी शिफ्ट में दुर्घटना का खतरा बढ़ता है — आराम करें और पानी पिएँ।",
        "best_platform": "{platform} पर आपको प्रति घंटा सबसे ज़्यादा मिलता है। मौका हो तो इसे चुनें।",
    },
}


def alert_message(alert: Alert, lang: str) -> str:
    """Human-readable alert text in English or Hindi."""
    templates = _ALERT_TEXT.get(lang, _ALERT_TEXT["en"])
    data = dict(alert.data)
    if "days" in data:
        data["days"] = ", ".join(data["days"])
    for key in ("this_week", "last_week", "amount"):
        if key in data:
            data[key] = money(data[key])
    return templates[alert.code].format(**data)


def offline_explanation(summary: EarningsSummary, lang: str) -> str:
    """Template explanation used when Gemini is unavailable."""
    if summary.days_worked == 0:
        return (
            "अभी कोई कमाई दर्ज नहीं है। रोज़ की कमाई, घंटे और खर्च जोड़ें।"
            if lang == "hi"
            else "No earnings logged yet. Add each day's pay, hours and costs to see your real income."
        )
    rate = money(summary.net_per_hour)
    if lang == "hi":
        lines = [
            f"{summary.days_worked} दिनों में आपकी असली कमाई (खर्च और कटौती के बाद): {money(summary.net_earnings)}",
            f"- प्रति घंटा: {rate}",
            f"- कुल खर्च: {money(summary.total_expenses)}, प्लेटफॉर्म कटौती: {money(summary.total_deductions)}",
        ]
    else:
        lines = [
            f"Your real take-home over {summary.days_worked} days (after costs and deductions): {money(summary.net_earnings)}",
            f"- Per hour: {rate}",
            f"- Total costs: {money(summary.total_expenses)}, platform deductions: {money(summary.total_deductions)}",
        ]
    lines += [f"- {alert_message(a, lang)}" for a in summary.alerts]
    return "\n".join(lines)
