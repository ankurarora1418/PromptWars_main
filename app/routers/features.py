"""The five feature modules: earnings, safety, schemes, documents and grievances."""

from dataclasses import asdict

from fastapi import APIRouter, Depends, HTTPException

from app.config import Settings
from app.languages import offline_language
from app.routers.deps import ai_answer, get_ai, get_app_settings
from app.schemas import (
    DocumentRequest,
    EarningsRequest,
    GrievanceRequest,
    SafetyRequest,
    SchemeExplainRequest,
    SchemesRequest,
)
from app.services import documents, grievance, knowledge
from app.services.ai_client import AIClient, ImageInput
from app.services.earnings import alert_message, offline_explanation, summarize
from app.services.eligibility import match_schemes, offline_scheme_explanation, scheme_facts
from app.services.pii import mask_pii
from app.services.safety import select_tips

router = APIRouter(prefix="/api", tags=["features"])

_PRIVACY_NOTE = {
    "en": "For your privacy we hid these before sending: {items}.",
    "hi": "आपकी निजता के लिए भेजने से पहले ये छिपाए गए: {items}।",
}


def _emergency_numbers(lang: str) -> list[dict]:
    lines = knowledge.helplines()["helplines"]
    return [
        {"number": lines[key]["number"], "name": knowledge.localized(lines[key]["name"], lang)}
        for key in ("emergency", "ambulance", "women", "cyber")
    ]


# --- Earnings -----------------------------------------------------------------------------


@router.post("/earnings/summary")
async def earnings_summary(req: EarningsRequest, ai: AIClient = Depends(get_ai)) -> dict:
    """Exact earnings maths plus a plain-language explanation."""
    lang = offline_language(req.profile.language)
    summary = summarize(req.entries)
    alerts = [{**asdict(a), "message": alert_message(a, lang)} for a in summary.alerts]
    facts = summary.to_dict()
    facts.pop("daily", None)
    facts["alerts"] = [a["message"] for a in alerts]
    facts["currency"] = "INR"
    explanation = None
    if summary.days_worked:
        explanation = await ai_answer(
            ai,
            task="earnings",
            language=req.profile.language,
            facts=facts,
            worker_input=mask_pii(req.question).text if req.question else None,
            offline_text=offline_explanation(summary, lang),
        )
    data = summary.to_dict()
    data["alerts"] = alerts
    return {"summary": data, "explanation": explanation}


# --- Safety -------------------------------------------------------------------------------


@router.post("/safety")
async def safety(req: SafetyRequest, ai: AIClient = Depends(get_ai)) -> dict:
    """Context-aware tips; optionally answers a safety question with Gemini."""
    lang = offline_language(req.profile.language)
    tips = select_tips(req.profile, req.hour, list(req.conditions), limit=5)
    answer = None
    if req.question:
        answer = await ai_answer(
            ai,
            task="safety",
            language=req.profile.language,
            facts={
                "work_type": req.profile.work_type,
                "local_hour": req.hour,
                "conditions": list(req.conditions),
                "suggested_tips": [tip.text for tip in tips],
                "emergency_number": "112",
            },
            worker_input=mask_pii(req.question).text,
            offline_text="\n".join(f"- {tip.text}" for tip in tips),
        )
    return {
        "tips": [asdict(tip) for tip in tips],
        "helplines": _emergency_numbers(lang),
        "answer": answer,
    }


# --- Schemes ------------------------------------------------------------------------------


@router.post("/schemes/match")
async def schemes_match(req: SchemesRequest) -> dict:
    """Every scheme with eligible / next_step / not_eligible status and reasons."""
    return {"schemes": [asdict(m) for m in match_schemes(req.profile)]}


@router.post("/schemes/explain")
async def schemes_explain(req: SchemeExplainRequest, ai: AIClient = Depends(get_ai)) -> dict:
    """Plain-language explanation of one scheme, grounded on the curated record."""
    match = scheme_facts(req.scheme_id, req.profile)
    if match is None:
        raise HTTPException(status_code=404, detail="Unknown scheme")
    lang = offline_language(req.profile.language)
    answer = await ai_answer(
        ai,
        task="scheme",
        language=req.profile.language,
        facts=asdict(match),
        worker_input=mask_pii(req.question).text if req.question else None,
        offline_text=offline_scheme_explanation(match, lang),
    )
    return {"scheme": asdict(match), "answer": answer}


# --- Documents ----------------------------------------------------------------------------


@router.post("/documents/checklist")
async def documents_checklist(req: SchemeExplainRequest) -> dict:
    """Documents needed to apply for a scheme."""
    result = documents.checklist(req.scheme_id, req.profile)
    if result is None:
        raise HTTPException(status_code=404, detail="Unknown scheme")
    return result


@router.post("/documents/explain")
async def documents_explain(
    req: DocumentRequest,
    ai: AIClient = Depends(get_ai),
    settings: Settings = Depends(get_app_settings),
) -> dict:
    """Explain a pasted document or a photo of one. Personal numbers are masked first."""
    lang = offline_language(req.profile.language)
    image = None
    if req.image_base64:
        try:
            data = documents.decode_image(req.image_base64, req.image_mime, settings.max_image_bytes)
        except documents.InvalidImageError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        image = ImageInput(data=data, mime_type=req.image_mime)

    worker_text = "\n\n".join(part for part in (req.text, req.question) if part)
    masked = mask_pii(worker_text) if worker_text else None
    note = None
    if masked and masked.masked_anything:
        note = _PRIVACY_NOTE[lang].format(items=", ".join(sorted(masked.found)))
    answer = await ai_answer(
        ai,
        task="document",
        language=req.profile.language,
        facts={"has_photo": image is not None},
        worker_input=masked.text if masked else "(see attached photo)",
        image=image,
        offline_text=documents.offline_document_help(lang),
        privacy_note=note,
    )
    return {"answer": answer, "masked": masked.found if masked else {}}


# --- Grievance ----------------------------------------------------------------------------


@router.post("/grievance/draft")
async def grievance_draft(req: GrievanceRequest, ai: AIClient = Depends(get_ai)) -> dict:
    """Draft a complaint letter and say where to file it."""
    lang = offline_language(req.profile.language)
    masked = mask_pii(req.description)
    safe_req = req.model_copy(
        update={
            "description": masked.text,
            "evidence": [mask_pii(item).text for item in req.evidence],
        }
    )
    answer = await ai_answer(
        ai,
        task="grievance",
        language=req.profile.language,
        facts=grievance.grievance_facts(safe_req),
        worker_input=masked.text,
        offline_text=grievance.offline_draft(safe_req),
    )
    return {
        "draft": answer,
        "where_to_file": grievance.issue_info(req.issue_type, lang),
        "placeholders": list(grievance.PLACEHOLDERS),
    }
