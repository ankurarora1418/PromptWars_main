"""Health, metadata, the personalised home screen and the free-form Ask box."""

from dataclasses import asdict

from fastapi import APIRouter, Depends, Query

from app.config import Settings
from app.languages import NATIVE_NAMES, UI_LANGUAGES, offline_language
from app.routers.deps import ai_answer, get_ai, get_app_settings
from app.schemas import INDIAN_STATES, ChatRequest, HomeRequest
from app.services import grievance
from app.services.ai_client import AIClient
from app.services.context_engine import build_cards
from app.services.earnings import alert_message, summarize
from app.services.eligibility import match_schemes
from app.services.intent import classify
from app.services.pii import mask_pii
from app.services.safety import select_tips

router = APIRouter(prefix="/api", tags=["core"])

_GENERAL_HELP = {
    "en": (
        "I can help you with:\n"
        "- Earnings: log daily pay and see what you really take home\n"
        "- Safety: tips for night, heat, rain and road safety\n"
        "- Schemes: government schemes and rights you qualify for\n"
        "- Documents: understand a notice, form or contract\n"
        "- Complaint: draft a letter about pay, deductions or a blocked ID"
    ),
    "hi": (
        "मैं इनमें मदद कर सकता हूँ:\n"
        "- कमाई: रोज़ की कमाई दर्ज करें और असली बचत देखें\n"
        "- सुरक्षा: रात, गर्मी, बारिश और सड़क सुरक्षा की सलाह\n"
        "- योजनाएँ: सरकारी योजनाएँ और अधिकार जिनके आप हकदार हैं\n"
        "- दस्तावेज़: नोटिस, फॉर्म या अनुबंध समझें\n"
        "- शिकायत: भुगतान, कटौती या ब्लॉक आईडी पर पत्र बनाएँ"
    ),
}

_ROUTE_HINT = {
    "en": "Open the {module} section for detailed help.",
    "hi": "विस्तार से मदद के लिए {module} सेक्शन खोलें।",
}
_MODULE_NAMES = {
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


@router.get("/health")
async def health(settings: Settings = Depends(get_app_settings)) -> dict:
    """Liveness probe. Reports whether Gemini is configured (never the key itself)."""
    return {"status": "ok", "ai_enabled": settings.ai_enabled, "model": settings.gemini_model}


@router.get("/meta")
async def meta(lang: str = Query(default="en", max_length=5)) -> dict:
    """Static options for the UI: languages, states, complaint types."""
    lang = offline_language(lang)
    return {
        "languages": [{"code": code, "name": name} for code, name in NATIVE_NAMES.items()],
        "ui_languages": list(UI_LANGUAGES),
        "states": list(INDIAN_STATES),
        "issue_types": grievance.issue_types(lang),
    }


@router.post("/home")
async def home(req: HomeRequest) -> dict:
    """Ranked "Today for you" cards for this worker's context."""
    return {"cards": [asdict(card) for card in build_cards(req.profile, req.hour, req.entries)]}


def _chat_facts(intent: str, req: ChatRequest) -> dict:
    """Module-specific facts so the chat answer is grounded, not invented."""
    lang = offline_language(req.profile.language)
    if intent == "earnings":
        summary = summarize(req.entries)
        data = summary.to_dict()
        data.pop("daily", None)
        data["alerts"] = [alert_message(a, lang) for a in summary.alerts]
        return {"earnings_summary": data}
    if intent == "safety":
        tips = select_tips(req.profile, hour=12, conditions=[], limit=6)
        return {"safety_tips": [tip.text for tip in tips], "emergency_number": "112"}
    if intent == "schemes":
        return {
            "schemes": [
                {"name": m.name, "status": m.status, "benefit": m.benefit, "how_to_apply": m.how_to_apply}
                for m in match_schemes(req.profile)
                if m.status != "not_eligible"
            ]
        }
    if intent == "grievance":
        return {"complaint_types": [t["label"] for t in grievance.issue_types(lang)]}
    return {"app_sections": list(_MODULE_NAMES["en"].values())}


@router.post("/chat")
async def chat(req: ChatRequest, ai: AIClient = Depends(get_ai)) -> dict:
    """Free-form question: route it to a module, then answer with that module's facts."""
    lang = offline_language(req.profile.language)
    intent = classify(req.message).name
    masked = mask_pii(req.message)
    facts = _chat_facts(intent, req)
    facts["worker_profile"] = {
        "work_type": req.profile.work_type,
        "state": req.profile.state,
        "shift": req.profile.shift,
    }
    if intent == "general":
        offline = _GENERAL_HELP[lang]
    else:
        offline = _ROUTE_HINT[lang].format(module=_MODULE_NAMES[lang][intent])
    answer = await ai_answer(
        ai,
        task="chat",
        language=req.profile.language,
        facts=facts,
        worker_input=masked.text,
        offline_text=offline,
    )
    return {"intent": intent, "suggested_module": None if intent == "general" else intent, "answer": answer}
