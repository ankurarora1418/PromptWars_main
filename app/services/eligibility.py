"""Rule-based scheme matching.

Eligibility is decided by explicit rules from ``schemes.json``, not by the LLM, so the result
is predictable and testable. Each scheme comes back as ``eligible``, ``next_step`` (eligible
after one action, e.g. registering on e-Shram) or ``not_eligible`` with the reasons.
"""

from dataclasses import dataclass, field

from app.languages import offline_language
from app.schemas import Profile
from app.services import knowledge

STATUS_ORDER = {"eligible": 0, "next_step": 1, "not_eligible": 2}

_REASONS = {
    "en": {
        "age_unknown": "Add your age to check this",
        "too_young": "Minimum age is {min_age}",
        "too_old": "Maximum joining age is {max_age}",
        "income": "Monthly income must be ₹{max_monthly_income} or less",
        "epfo": "Not for EPFO/ESIC members",
        "tax": "Not for income tax payers",
        "bank": "Needs a bank account — open a free Jan Dhan account first",
        "work_type": "Only for platform workers (delivery, cab, bike-taxi)",
        "state": "Only for workers in {states}",
        "eshram": "Register on e-Shram first",
    },
    "hi": {
        "age_unknown": "जाँचने के लिए अपनी उम्र जोड़ें",
        "too_young": "न्यूनतम उम्र {min_age} साल है",
        "too_old": "शामिल होने की अधिकतम उम्र {max_age} साल है",
        "income": "मासिक आय ₹{max_monthly_income} या कम होनी चाहिए",
        "epfo": "EPFO/ESIC सदस्यों के लिए नहीं",
        "tax": "आयकर देने वालों के लिए नहीं",
        "bank": "बैंक खाता ज़रूरी है — पहले मुफ्त जन धन खाता खोलें",
        "work_type": "केवल प्लेटफॉर्म कामगारों के लिए (डिलीवरी, कैब, बाइक-टैक्सी)",
        "state": "केवल {states} के कामगारों के लिए",
        "eshram": "पहले ई-श्रम पर पंजीकरण करें",
    },
}


@dataclass
class SchemeMatch:
    id: str
    category: str
    name: str
    summary: str
    benefit: str
    cost: str
    how_to_apply: str
    documents: list[str]
    official_url: str
    status: str
    reasons: list[str] = field(default_factory=list)
    next_step: str | None = None  # "scheme:eshram" when a prerequisite is missing


def _check(rules: dict, profile: Profile) -> tuple[list[str], list[str]]:
    """Return (blocking reason codes, fixable reason codes)."""
    blocking: list[str] = []
    fixable: list[str] = []
    if "min_age" in rules or "max_age" in rules:
        if profile.age is None:
            fixable.append("age_unknown")
        else:
            if profile.age < rules.get("min_age", 0):
                blocking.append("too_young")
            if profile.age > rules.get("max_age", 200):
                blocking.append("too_old")
    limit = rules.get("max_monthly_income")
    if limit is not None and profile.monthly_income is not None and profile.monthly_income > limit:
        blocking.append("income")
    if rules.get("exclude_epfo_esic") and profile.has_epfo_or_esic:
        blocking.append("epfo")
    if rules.get("exclude_income_tax") and profile.pays_income_tax:
        blocking.append("tax")
    if rules.get("work_types") and profile.work_type not in rules["work_types"]:
        blocking.append("work_type")
    if rules.get("states") and profile.state not in rules["states"]:
        blocking.append("state")
    if rules.get("requires_bank_account") and not profile.has_bank_account:
        fixable.append("bank")
    if rules.get("requires_eshram") and not profile.eshram_registered:
        fixable.append("eshram")
    return blocking, fixable


def match_schemes(profile: Profile) -> list[SchemeMatch]:
    """Evaluate every curated scheme for this worker, best matches first."""
    lang = offline_language(profile.language)
    reasons_text = _REASONS[lang]
    results: list[SchemeMatch] = []
    for scheme in knowledge.schemes():
        rules = scheme.get("rules", {})
        blocking, fixable = _check(rules, profile)
        if blocking:
            status = "not_eligible"
        elif fixable:
            status = "next_step"
        else:
            status = "eligible"
        fmt = {**rules, "states": ", ".join(rules.get("states", []))}
        reasons = [reasons_text[code].format(**fmt) for code in blocking + fixable]
        next_step = "scheme:eshram" if "eshram" in fixable else None
        doc_names = knowledge.document_names()
        results.append(
            SchemeMatch(
                id=scheme["id"],
                category=scheme["category"],
                name=knowledge.localized(scheme["name"], lang),
                summary=knowledge.localized(scheme["summary"], lang),
                benefit=knowledge.localized(scheme["benefit"], lang),
                cost=knowledge.localized(scheme["cost"], lang),
                how_to_apply=knowledge.localized(scheme["how_to_apply"], lang),
                documents=[knowledge.localized(doc_names[d], lang) for d in scheme["documents"]],
                official_url=scheme["official_url"],
                status=status,
                reasons=reasons,
                next_step=next_step,
            )
        )
    results.sort(key=lambda m: STATUS_ORDER[m.status])
    return results


def scheme_facts(scheme_id: str, profile: Profile) -> SchemeMatch | None:
    """The match result for one scheme, or None if the id is unknown."""
    if scheme_id not in knowledge.scheme_by_id():
        return None
    return next(m for m in match_schemes(profile) if m.id == scheme_id)


def offline_scheme_explanation(match: SchemeMatch, lang: str) -> str:
    """Template explanation used when Gemini is unavailable."""
    if lang == "hi":
        lines = [
            match.summary,
            f"- लाभ: {match.benefit}",
            f"- खर्च: {match.cost}",
            f"- कैसे आवेदन करें: {match.how_to_apply}",
            f"- ज़रूरी दस्तावेज़: {', '.join(match.documents)}",
        ]
    else:
        lines = [
            match.summary,
            f"- You get: {match.benefit}",
            f"- Cost: {match.cost}",
            f"- How to apply: {match.how_to_apply}",
            f"- Documents: {', '.join(match.documents)}",
        ]
    lines += [f"- {reason}" for reason in match.reasons]
    return "\n".join(lines)
