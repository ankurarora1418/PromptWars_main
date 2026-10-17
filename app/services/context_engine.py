"""The "Today for you" decision engine.

Combines the worker's profile, local time, earnings and weekly goal into a ranked list of
action cards. Each card links to a module, which is how the app's workflows connect: a pay drop
leads to a complaint draft, a missing e-Shram registration leads to the scheme guide, an unsafe
weekly goal leads to the planner, and so on.

Every card carries a ``reason`` — a one-line, plain-language "why you are seeing this" — so the
decision is transparent to the worker and easy to audit.
"""

from dataclasses import dataclass, field
from datetime import date

from app.languages import offline_language
from app.schemas import EarningEntry, Profile
from app.services.earnings import EarningsSummary, alert_message, money, summarize
from app.services.eligibility import match_schemes
from app.services.planner import plan_message, plan_week
from app.services.safety import NIGHT_HOURS, select_tips

ROAD_WORK = {"delivery", "ride_driver"}
MAX_CARDS = 5

_TEXT = {
    "en": {
        "night_title": "Night shift safety",
        "pay_drop_title": "Your pay per hour dropped",
        "deduction_title": "High platform deductions",
        "long_hours_title": "You are working very long days",
        "eshram_title": "Register on e-Shram (free)",
        "eshram_body": "It unlocks government welfare, including ₹5 lakh hospital cover for platform workers.",
        "pmsby_title": "₹2 lakh accident cover for ₹20 a year",
        "pmsby_body": "PMSBY insurance through your bank protects you on the road.",
        "profile_title": "Complete your profile",
        "profile_body": "Add your age and income so we can find every scheme you qualify for.",
        "track_title": "Track today's earnings",
        "track_body": "Log your pay, hours and fuel to see what you really take home per hour.",
        "complaint_title": "Problem with pay or your ID?",
        "complaint_body": "Draft a clear complaint letter in your language in one minute.",
        "safety_title": "Today's safety tip",
        "goal_title": "Weekly goal: {pct}% done",
        "goal_unsafe_title": "Your weekly goal needs unsafe hours",
    },
    "hi": {
        "night_title": "रात की शिफ्ट में सुरक्षा",
        "pay_drop_title": "आपकी प्रति घंटा कमाई घटी है",
        "deduction_title": "प्लेटफॉर्म की कटौती ज़्यादा है",
        "long_hours_title": "आप बहुत लंबे दिन काम कर रहे हैं",
        "eshram_title": "ई-श्रम पर पंजीकरण करें (मुफ्त)",
        "eshram_body": "इससे सरकारी योजनाएँ मिलती हैं, जिसमें प्लेटफॉर्म कामगारों के लिए ₹5 लाख का अस्पताल कवर भी है।",
        "pmsby_title": "₹20 सालाना में ₹2 लाख दुर्घटना बीमा",
        "pmsby_body": "बैंक के ज़रिए PMSBY बीमा सड़क पर आपकी रक्षा करता है।",
        "profile_title": "अपनी प्रोफ़ाइल पूरी करें",
        "profile_body": "उम्र और आय जोड़ें ताकि हम आपकी हर योजना ढूँढ सकें।",
        "track_title": "आज की कमाई दर्ज करें",
        "track_body": "भुगतान, घंटे और ईंधन दर्ज करें और देखें कि प्रति घंटा असल में कितना बचता है।",
        "complaint_title": "भुगतान या आईडी में समस्या?",
        "complaint_body": "एक मिनट में अपनी भाषा में साफ़ शिकायत पत्र बनाएँ।",
        "safety_title": "आज की सुरक्षा सलाह",
        "goal_title": "साप्ताहिक लक्ष्य: {pct}% पूरा",
        "goal_unsafe_title": "आपके साप्ताहिक लक्ष्य के लिए असुरक्षित घंटे चाहिए",
    },
}


_REASONS = {
    "en": {
        "night_safety": "It is night and you work on the road.",
        "safety_tip": "Picked for your type of work and the time of day.",
        "pay_drop": "Your pay per hour this week is {drop_pct}% below last week.",
        "high_deductions": "Platform cuts are {share_pct}% of your earnings (above 20%).",
        "long_hours": "You logged days of 12 hours or more.",
        "goal": "You set a weekly goal of {goal}.",
        "eshram": "Your profile says you are not on e-Shram yet, and you qualify.",
        "pmsby": "You work on the road and qualify for this low-cost cover.",
        "profile": "Your age or income is missing, so some schemes cannot be checked.",
        "track": "You have not logged any earnings yet.",
        "complaint": "Always here if pay, deductions or your ID go wrong.",
    },
    "hi": {
        "night_safety": "अभी रात है और आप सड़क पर काम करते हैं।",
        "safety_tip": "आपके काम और दिन के समय के हिसाब से चुनी गई।",
        "pay_drop": "इस हफ्ते आपकी प्रति घंटा कमाई पिछले हफ्ते से {drop_pct}% कम है।",
        "high_deductions": "प्लेटफॉर्म की कटौती आपकी कमाई का {share_pct}% है (20% से ज़्यादा)।",
        "long_hours": "आपने 12 घंटे या उससे लंबे दिन दर्ज किए हैं।",
        "goal": "आपने {goal} का साप्ताहिक लक्ष्य रखा है।",
        "eshram": "प्रोफ़ाइल के अनुसार आप अभी ई-श्रम पर नहीं हैं, और आप पात्र हैं।",
        "pmsby": "आप सड़क पर काम करते हैं और इस सस्ते बीमे के पात्र हैं।",
        "profile": "आपकी उम्र या आय नहीं भरी है, इसलिए कुछ योजनाएँ जाँची नहीं जा सकतीं।",
        "track": "आपने अभी तक कोई कमाई दर्ज नहीं की है।",
        "complaint": "भुगतान, कटौती या आईडी में गड़बड़ी हो तो हमेशा उपलब्ध।",
    },
}

# Goal cards outrank most nudges when the plan is unsafe, and sink once the goal is met.
_GOAL_PRIORITY = {"unsafe": 83, "stretch": 66, "on_track": 64, "week_over": 46, "achieved": 45}


@dataclass
class Card:
    """One action on the home screen. ``reason`` explains why the engine chose it."""

    id: str
    priority: int
    title: str
    body: str
    module: str  # which screen the card opens
    params: dict = field(default_factory=dict)
    tone: str = "info"  # "info" | "warning" | "safety"
    reason: str = ""


def build_cards(
    profile: Profile,
    hour: int,
    entries: list[EarningEntry],
    today: date | None = None,
    summary: EarningsSummary | None = None,
) -> list[Card]:
    """Return up to ``MAX_CARDS`` cards, most important first.

    ``summary`` lets a caller that already summarised ``entries`` pass it in, so the earnings
    maths runs once per request.
    """
    lang = offline_language(profile.language)
    text = _TEXT[lang]
    reasons = _REASONS[lang]
    cards: list[Card] = []
    summary = summary or summarize(entries)
    alerts = {alert.code: alert for alert in summary.alerts}

    def add(card: Card, **reason_data: object) -> None:
        card.reason = reasons[card.id].format(**reason_data)
        cards.append(card)

    is_night = hour in NIGHT_HOURS or profile.shift == "night"
    tips = select_tips(profile, hour, [], long_hours="long_hours" in alerts, limit=1)
    if is_night and profile.work_type in ROAD_WORK and tips:
        add(Card("night_safety", 90, text["night_title"], tips[0].text, "safety", tone="safety"))
    elif tips:
        add(Card("safety_tip", 40, text["safety_title"], tips[0].text, "safety", tone="safety"))

    if "pay_drop" in alerts:
        alert = alerts["pay_drop"]
        add(
            Card(
                "pay_drop",
                85,
                text["pay_drop_title"],
                alert_message(alert, lang),
                "grievance",
                {"issue_type": "incentive_not_paid"},
                tone="warning",
            ),
            drop_pct=alert.data["drop_pct"],
        )
    if "high_deductions" in alerts:
        alert = alerts["high_deductions"]
        add(
            Card(
                "high_deductions",
                80,
                text["deduction_title"],
                alert_message(alert, lang),
                "grievance",
                {"issue_type": "wrong_deduction", "amount": alert.data["amount"]},
                tone="warning",
            ),
            share_pct=alert.data["share_pct"],
        )
    if "long_hours" in alerts:
        add(
            Card(
                "long_hours",
                70,
                text["long_hours_title"],
                alert_message(alerts["long_hours"], lang),
                "safety",
                tone="safety",
            )
        )

    if profile.weekly_goal and entries:
        plan = plan_week(profile.weekly_goal, entries, today or date.today())
        if plan.status in _GOAL_PRIORITY:
            unsafe = plan.status == "unsafe"
            title = (
                text["goal_unsafe_title"]
                if unsafe
                else text["goal_title"].format(pct=round(plan.progress * 100))
            )
            add(
                Card(
                    "goal",
                    _GOAL_PRIORITY[plan.status],
                    title,
                    plan_message(plan, lang),
                    "earnings",
                    {"status": plan.status},
                    tone="warning" if unsafe else "info",
                ),
                goal=money(plan.goal),
            )

    statuses = {match.id: match.status for match in match_schemes(profile)}
    if not profile.eshram_registered and statuses.get("eshram") == "eligible":
        add(Card("eshram", 75, text["eshram_title"], text["eshram_body"], "schemes", {"scheme_id": "eshram"}))
    if profile.work_type in ROAD_WORK and statuses.get("pmsby") == "eligible":
        add(Card("pmsby", 60, text["pmsby_title"], text["pmsby_body"], "schemes", {"scheme_id": "pmsby"}))
    if profile.age is None or profile.monthly_income is None:
        add(Card("profile", 55, text["profile_title"], text["profile_body"], "profile"))
    if not entries:
        add(Card("track", 50, text["track_title"], text["track_body"], "earnings"))
    add(Card("complaint", 20, text["complaint_title"], text["complaint_body"], "grievance"))

    cards.sort(key=lambda card: -card.priority)
    return cards[:MAX_CARDS]
