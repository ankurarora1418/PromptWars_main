"""The "Ask Saathi" brain: route a question, gather grounded facts, and answer offline too.

Flow for every question:

1. :func:`rank_intents` picks up to two modules the question touches (e.g. a late payout and a
   blocked ID touch *earnings* and *grievance*).
2. :func:`build_context` gathers grounded facts for those modules **plus** a snapshot of what
   Saathi already decided matters for this worker right now (the top home cards and why).
3. Gemini explains those facts; if it is unavailable, :func:`offline_answer` builds a useful
   answer from the very same facts, so the assistant still helps with no network or quota.
"""

from dataclasses import dataclass, field
from datetime import date
from typing import Any

from app.languages import offline_language
from app.schemas import ChatRequest
from app.services import grievance
from app.services.context_engine import build_cards
from app.services.earnings import EarningsSummary, alert_message, offline_explanation, summarize
from app.services.eligibility import match_schemes
from app.services.intent import rank_intents
from app.services.planner import plan_message, plan_week
from app.services.safety import select_tips

MAX_INTENTS = 2
MAX_SAFETY_TIPS = 3
MAX_PRIORITIES = 3

MODULE_NAMES = {
    "en": {
        "earnings": "Earnings",
        "safety": "Safety",
        "schemes": "Schemes",
        "documents": "Documents",
        "grievance": "Complaint",
    },
    "hi": {
        "earnings": "कमाई",
        "safety": "सुरक्षा",
        "schemes": "योजनाएँ",
        "documents": "दस्तावेज़",
        "grievance": "शिकायत",
    },
}

_TEXT = {
    "en": {
        "general": "I can help with earnings, safety, government schemes, documents and complaints.",
        "priorities": "Right now, for you:",
        "no_entries": "You have not logged any earnings yet. Add a day in Earnings to see your real take-home.",
        "eligible": "Schemes you qualify for: {names}.",
        "next_step": "One step away: {names}.",
        "no_schemes": "Complete your profile (age, income) so I can check schemes for you.",
        "danger": "If you are in danger or hurt, call 112 now.",
        "documents": "Open Documents and paste the text or take a photo; I will explain it simply.",
        "grievance": "For {label}, you can go to:{file_with}",
        "grievance_generic": "Open Complaint to draft a clear letter and see where to send it.",
    },
    "hi": {
        "general": "मैं कमाई, सुरक्षा, सरकारी योजनाओं, दस्तावेज़ों और शिकायतों में मदद कर सकता हूँ।",
        "priorities": "अभी आपके लिए ज़रूरी:",
        "no_entries": "आपने अभी कोई कमाई दर्ज नहीं की है। असली बचत देखने के लिए कमाई में एक दिन जोड़ें।",
        "eligible": "जिन योजनाओं के आप पात्र हैं: {names}।",
        "next_step": "बस एक कदम दूर: {names}।",
        "no_schemes": "प्रोफ़ाइल (उम्र, आय) पूरी करें ताकि मैं योजनाएँ जाँच सकूँ।",
        "danger": "अगर आप खतरे में हैं या चोट लगी है, तो अभी 112 पर कॉल करें।",
        "documents": "दस्तावेज़ खोलें और टेक्स्ट चिपकाएँ या फोटो लें; मैं आसान शब्दों में समझाऊँगा।",
        "grievance": "{label} के लिए आप यहाँ जा सकते हैं:{file_with}",
        "grievance_generic": "साफ़ पत्र बनाने और कहाँ भेजना है जानने के लिए शिकायत खोलें।",
    },
}

# Words that point to a specific complaint type, so the offline answer can name where to file.
_ISSUE_HINTS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("deactivation", ("blocked", "deactivat", "id band", "ब्लॉक")),
    ("wrong_deduction", ("deduct", "penalty", "cut", "कटौती")),
    ("incentive_not_paid", ("incentive", "bonus", "इंसेंटिव")),
    ("unpaid_earnings", ("not paid", "payout", "late pay", "unpaid", "भुगतान")),
    ("employer_wage_theft", ("wage", "contractor", "thekedar", "मज़दूरी")),
    ("harassment", ("harass", "abuse", "उत्पीड़न")),
    ("accident_injury", ("accident", "injur", "दुर्घटना")),
    ("payment_fraud", ("fraud", "scam", "धोखा")),
)


@dataclass
class AssistantContext:
    """Everything the assistant knows for one question: routing, facts and the offline answer."""

    intents: list[str]
    facts: dict[str, Any]
    offline_text: str
    suggested_modules: list[str] = field(default_factory=list)


def _issue_from_text(message: str) -> str | None:
    text = message.lower()
    for issue, hints in _ISSUE_HINTS:
        if any(hint in text for hint in hints):
            return issue
    return None


def _earnings_part(
    req: ChatRequest, lang: str, today: date, summary: EarningsSummary
) -> tuple[dict, list[str]]:
    if not summary.days_worked:
        return {"earnings_summary": "no days logged yet"}, [_TEXT[lang]["no_entries"]]
    data = summary.to_dict()
    data.pop("daily", None)
    data["alerts"] = [alert_message(a, lang) for a in summary.alerts]
    facts: dict[str, Any] = {"earnings_summary": data}
    lines = [offline_explanation(summary, lang)]
    if req.profile.weekly_goal:
        message = plan_message(plan_week(req.profile.weekly_goal, req.entries, today), lang)
        facts["weekly_goal_plan"] = message
        lines.append(message)
    return facts, lines


def _safety_part(req: ChatRequest, lang: str) -> tuple[dict, list[str]]:
    tips = [tip.text for tip in select_tips(req.profile, req.hour, [], limit=MAX_SAFETY_TIPS)]
    lines = [_TEXT[lang]["danger"], *(f"- {tip}" for tip in tips)]
    return {"safety_tips": tips, "emergency_number": "112"}, lines


def _schemes_part(req: ChatRequest, lang: str) -> tuple[dict, list[str]]:
    matches = [m for m in match_schemes(req.profile) if m.status != "not_eligible"]
    facts = {
        "schemes": [
            {"name": m.name, "status": m.status, "benefit": m.benefit, "how_to_apply": m.how_to_apply}
            for m in matches
        ]
    }
    eligible = [m.name for m in matches if m.status == "eligible"]
    pending = [m.name for m in matches if m.status == "next_step"]
    lines = []
    if eligible:
        lines.append(_TEXT[lang]["eligible"].format(names=", ".join(eligible)))
    if pending:
        lines.append(_TEXT[lang]["next_step"].format(names=", ".join(pending)))
    return facts, lines or [_TEXT[lang]["no_schemes"]]


def _grievance_part(req: ChatRequest, lang: str) -> tuple[dict, list[str]]:
    issue = _issue_from_text(req.message)
    facts: dict[str, Any] = {"complaint_types": [t["label"] for t in grievance.issue_types(lang)]}
    if issue is None:
        return facts, [_TEXT[lang]["grievance_generic"]]
    info = grievance.issue_info(issue, lang)
    facts["likely_issue"] = info
    file_with = info["file_with"]
    routes = file_with if isinstance(file_with, list) else [file_with]
    lines = [_TEXT[lang]["grievance"].format(label=info["label"], file_with="")]
    lines += [f"- {route}" for route in routes]
    lines += [f"- {line['name']}: {line['number']}" for line in info["helplines"]]
    lines.append(_TEXT[lang]["grievance_generic"])
    return facts, lines


def build_context(req: ChatRequest, today: date | None = None) -> AssistantContext:
    """Route the question and gather grounded facts plus an offline answer."""
    lang = offline_language(req.profile.language)
    today = today or req.today or date.today()
    intents = [intent.name for intent in rank_intents(req.message, limit=MAX_INTENTS)]

    summary = summarize(req.entries)  # computed once, shared by the cards and the earnings facts
    cards = build_cards(req.profile, req.hour, req.entries, today, summary=summary)
    priorities = [{"title": c.title, "why": c.reason} for c in cards[:MAX_PRIORITIES]]
    facts: dict[str, Any] = {
        "worker_profile": {
            "work_type": req.profile.work_type,
            "state": req.profile.state,
            "shift": req.profile.shift,
            "on_eshram": req.profile.eshram_registered,
            "weekly_goal_set": req.profile.weekly_goal is not None,
        },
        "local_hour": req.hour,
        "current_priorities": priorities,
        "app_sections": list(MODULE_NAMES["en"].values()),
    }

    lines: list[str] = []
    for intent in intents:
        if intent == "earnings":
            part_facts, part_lines = _earnings_part(req, lang, today, summary)
        elif intent == "safety":
            part_facts, part_lines = _safety_part(req, lang)
        elif intent == "schemes":
            part_facts, part_lines = _schemes_part(req, lang)
        elif intent == "grievance":
            part_facts, part_lines = _grievance_part(req, lang)
        else:  # documents
            part_facts, part_lines = {}, [_TEXT[lang]["documents"]]
        facts.update(part_facts)
        lines += part_lines

    if not intents:
        lines = [_TEXT[lang]["general"], _TEXT[lang]["priorities"]]
        lines += [f"- {p['title']}: {p['why']}" for p in priorities]

    # Nothing matched: point to the worker's top priority that opens an app section.
    sections = [card.module for card in cards if card.module in MODULE_NAMES["en"]]
    suggested = list(intents) if intents else sections[:1]
    return AssistantContext(
        intents=intents or ["general"],
        facts=facts,
        offline_text="\n".join(lines),
        suggested_modules=suggested,
    )
