"""The "Today for you" decision engine.

Combines the worker's profile, local time and earnings into a ranked list of action cards.
Each card links to a module, which is how the app's workflows connect: a pay drop leads to a
complaint draft, a missing e-Shram registration leads to the scheme guide, and so on.
"""

from dataclasses import dataclass, field

from app.languages import offline_language
from app.schemas import EarningEntry, Profile
from app.services.earnings import alert_message, summarize
from app.services.eligibility import match_schemes
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
    },
}


@dataclass
class Card:
    id: str
    priority: int
    title: str
    body: str
    module: str  # which screen the card opens
    params: dict = field(default_factory=dict)
    tone: str = "info"  # "info" | "warning" | "safety"


def build_cards(profile: Profile, hour: int, entries: list[EarningEntry]) -> list[Card]:
    """Return up to ``MAX_CARDS`` cards, most important first."""
    lang = offline_language(profile.language)
    text = _TEXT[lang]
    cards: list[Card] = []
    summary = summarize(entries)
    alerts = {alert.code: alert for alert in summary.alerts}

    is_night = hour in NIGHT_HOURS or profile.shift == "night"
    tips = select_tips(profile, hour, [], long_hours="long_hours" in alerts, limit=1)
    if is_night and profile.work_type in ROAD_WORK and tips:
        cards.append(Card("night_safety", 90, text["night_title"], tips[0].text, "safety", tone="safety"))
    elif tips:
        cards.append(Card("safety_tip", 40, text["safety_title"], tips[0].text, "safety", tone="safety"))

    if "pay_drop" in alerts:
        cards.append(
            Card(
                "pay_drop",
                85,
                text["pay_drop_title"],
                alert_message(alerts["pay_drop"], lang),
                "grievance",
                {"issue_type": "incentive_not_paid"},
                tone="warning",
            )
        )
    if "high_deductions" in alerts:
        alert = alerts["high_deductions"]
        cards.append(
            Card(
                "high_deductions",
                80,
                text["deduction_title"],
                alert_message(alert, lang),
                "grievance",
                {"issue_type": "wrong_deduction", "amount": alert.data["amount"]},
                tone="warning",
            )
        )
    if "long_hours" in alerts:
        cards.append(
            Card(
                "long_hours",
                70,
                text["long_hours_title"],
                alert_message(alerts["long_hours"], lang),
                "safety",
                tone="safety",
            )
        )

    statuses = {match.id: match.status for match in match_schemes(profile)}
    if not profile.eshram_registered and statuses.get("eshram") == "eligible":
        cards.append(
            Card("eshram", 75, text["eshram_title"], text["eshram_body"], "schemes", {"scheme_id": "eshram"})
        )
    if profile.work_type in ROAD_WORK and statuses.get("pmsby") == "eligible":
        cards.append(
            Card("pmsby", 60, text["pmsby_title"], text["pmsby_body"], "schemes", {"scheme_id": "pmsby"})
        )
    if profile.age is None or profile.monthly_income is None:
        cards.append(Card("profile", 55, text["profile_title"], text["profile_body"], "profile"))
    if not entries:
        cards.append(Card("track", 50, text["track_title"], text["track_body"], "earnings"))
    cards.append(Card("complaint", 20, text["complaint_title"], text["complaint_body"], "grievance"))

    cards.sort(key=lambda card: -card.priority)
    return cards[:MAX_CARDS]
