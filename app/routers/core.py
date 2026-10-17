"""Health, metadata, the personalised home screen and the free-form Ask box."""

from dataclasses import asdict

from fastapi import APIRouter, Depends, Query

from app.config import Settings
from app.languages import NATIVE_NAMES, UI_LANGUAGES, offline_language
from app.routers.deps import ai_answer, get_ai, get_app_settings
from app.schemas import INDIAN_STATES, ChatRequest, HomeRequest
from app.services import grievance
from app.services.ai_client import AIClient
from app.services.assistant import build_context
from app.services.context_engine import build_cards
from app.services.pii import mask_pii

router = APIRouter(prefix="/api", tags=["core"])


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
    return {"cards": [asdict(card) for card in build_cards(req.profile, req.hour, req.entries, req.today)]}


@router.post("/chat")
async def chat(req: ChatRequest, ai: AIClient = Depends(get_ai)) -> dict:
    """Free-form question: route to up to two modules, ground the answer in this worker's context.

    The offline answer is built from the same facts, so the assistant stays useful when Gemini
    is unavailable.
    """
    context = build_context(req)
    answer = await ai_answer(
        ai,
        task="chat",
        language=req.profile.language,
        facts=context.facts,
        worker_input=mask_pii(req.message).text,
        offline_text=context.offline_text,
    )
    return {
        "intent": context.intents[0],
        "intents": context.intents,
        "suggested_module": context.suggested_modules[0] if context.suggested_modules else None,
        "suggested_modules": context.suggested_modules,
        "answer": answer,
    }
