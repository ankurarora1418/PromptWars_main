"""Route a free-form question to the right module.

A transparent keyword scorer (English, Hindi and Hinglish) is used instead of an extra LLM call:
it is instant, free, deterministic and easy to test. Gemini then answers with that module's facts.
"""

import re
from dataclasses import dataclass

INTENTS = ("earnings", "safety", "schemes", "documents", "grievance")

_KEYWORDS: dict[str, tuple[str, ...]] = {
    "earnings": (
        "earn",
        "earning",
        "income",
        "payout",
        "salary",
        "pay",
        "money",
        "kamai",
        "paisa",
        "paise",
        "hourly",
        "per hour",
        "fuel",
        "petrol",
        "expense",
        "kharcha",
        "tips",
        "commission",
        "कमाई",
        "पैसा",
        "पैसे",
        "खर्च",
        "आमदनी",
        "पेट्रोल",
    ),
    "safety": (
        "safe",
        "safety",
        "accident",
        "helmet",
        "night",
        "heat",
        "rain",
        "danger",
        "unsafe",
        "sos",
        "injury",
        "hurt",
        "garmi",
        "baarish",
        "suraksha",
        "सुरक्षा",
        "दुर्घटना",
        "हेलमेट",
        "रात",
        "गर्मी",
        "बारिश",
        "खतरा",
        "चोट",
    ),
    "schemes": (
        "scheme",
        "yojana",
        "pension",
        "insurance",
        "bima",
        "e-shram",
        "eshram",
        "ayushman",
        "welfare",
        "government",
        "sarkari",
        "benefit",
        "right",
        "rights",
        "law",
        "pm-sym",
        "pmsby",
        "pmjjby",
        "योजना",
        "पेंशन",
        "बीमा",
        "ई-श्रम",
        "आयुष्मान",
        "सरकारी",
        "अधिकार",
    ),
    "documents": (
        "document",
        "documents",
        "paper",
        "form",
        "notice",
        "letter",
        "contract",
        "agreement",
        "kagaz",
        "aadhaar",
        "certificate",
        "explain this",
        "दस्तावेज़",
        "कागज़",
        "फॉर्म",
        "नोटिस",
        "अनुबंध",
    ),
    "grievance": (
        "complaint",
        "complain",
        "grievance",
        "dispute",
        "blocked",
        "deactivated",
        "deactivation",
        "id band",
        "not paid",
        "unpaid",
        "deduction",
        "penalty",
        "fine",
        "cheated",
        "fraud",
        "harass",
        "shikayat",
        "shikayaat",
        "शिकायत",
        "ब्लॉक",
        "कटौती",
        "जुर्माना",
        "धोखा",
        "उत्पीड़न",
    ),
}

# Phrases that signal a dispute even when an earnings word is also present.
_STRONG = {
    "grievance": ("not paid", "deactivat", "blocked", "complain", "शिकायत", "fraud"),
}


@dataclass(frozen=True)
class Intent:
    name: str  # one of INTENTS or "general"
    score: int


def _count(text: str, words: tuple[str, ...]) -> int:
    total = 0
    for word in words:
        if word.isascii():
            total += len(re.findall(rf"\b{re.escape(word)}", text))
        else:
            total += text.count(word)
    return total


def classify(message: str) -> Intent:
    """Return the best-matching module for ``message``, or ``general``."""
    text = message.lower()
    scores = {name: _count(text, words) for name, words in _KEYWORDS.items()}
    for name, phrases in _STRONG.items():
        scores[name] += 2 * sum(1 for p in phrases if p in text)
    best = max(INTENTS, key=lambda name: scores[name])
    if scores[best] == 0:
        return Intent("general", 0)
    return Intent(best, scores[best])
