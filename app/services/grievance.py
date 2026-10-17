"""Grievance letters: where to file, and an offline template draft.

The worker's name, phone and ID are never sent to the server. Drafts use placeholders that the
browser fills in locally from what the worker typed.
"""

from app.languages import offline_language
from app.schemas import GrievanceRequest
from app.services import knowledge

PLACEHOLDERS = ("[YOUR NAME]", "[YOUR PHONE]", "[YOUR WORKER ID]")


def issue_info(issue_type: str, lang: str) -> dict:
    """Label, filing route and emergency numbers for an issue type."""
    data = knowledge.helplines()
    issue = data["issues"][issue_type]
    numbers = [
        {
            "number": data["helplines"][key]["number"],
            "name": knowledge.localized(data["helplines"][key]["name"], lang),
        }
        for key in issue["helplines"]
    ]
    return {
        "issue_type": issue_type,
        "label": knowledge.localized(issue["label"], lang),
        "file_with": knowledge.localized(issue["file_with"], lang),
        "helplines": numbers,
    }


def issue_types(lang: str) -> list[dict]:
    """All issue types with labels, for the form dropdown."""
    issues = knowledge.helplines()["issues"]
    return [{"id": key, "label": knowledge.localized(v["label"], lang)} for key, v in issues.items()]


def grievance_facts(req: GrievanceRequest) -> dict:
    """Structured facts given to the LLM to draft the letter."""
    lang = offline_language(req.profile.language)
    info = issue_info(req.issue_type, lang)
    return {
        "issue": info["label"],
        "complaint_to": req.against,
        "incident_date": req.incident_date.isoformat() if req.incident_date else "not given",
        "amount_rupees": req.amount,
        "evidence": req.evidence or ["none listed"],
        "worker_work_type": req.profile.work_type,
        "worker_state": req.profile.state,
        "where_to_file": info["file_with"],
    }


def offline_draft(req: GrievanceRequest) -> str:
    """Template complaint letter used when Gemini is unavailable."""
    lang = offline_language(req.profile.language)
    info = issue_info(req.issue_type, "en")
    date_text = req.incident_date.strftime("%d %B %Y") if req.incident_date else "[DATE]"
    amount_text = f"₹{req.amount:,.0f}" if req.amount else ""
    evidence = "\n".join(f"- {item}" for item in req.evidence) or "- [Add screenshots / receipts]"
    english = (
        f"To: {req.against} — Support / Grievance Officer\n"
        f"Subject: Complaint — {info['label']}{' of ' + amount_text if amount_text else ''}\n\n"
        f"Dear Sir/Madam,\n\n"
        f"I, [YOUR NAME] (Worker ID: [YOUR WORKER ID]), work with you as a {req.profile.work_type.replace('_', ' ')} "
        f"worker in {req.profile.state}. On {date_text}, the following happened:\n\n"
        f"{req.description}\n\n"
        f"Evidence:\n{evidence}\n\n"
        f"I request you to resolve this{' and pay me ' + amount_text if amount_text else ''} within 7 days "
        f"and reply to me in writing. If it is not resolved, I will take it to the appropriate authority.\n\n"
        f"Thank you,\n[YOUR NAME]\nPhone: [YOUR PHONE]"
    )
    if lang != "hi":
        return english
    hindi = (
        f"सेवा में: {req.against} — सपोर्ट / शिकायत अधिकारी\n"
        f"विषय: शिकायत — {issue_info(req.issue_type, 'hi')['label']}{' ' + amount_text if amount_text else ''}\n\n"
        f"महोदय/महोदया,\n\n"
        f"मैं, [YOUR NAME] (वर्कर आईडी: [YOUR WORKER ID]), {req.profile.state} में आपके साथ काम करता/करती हूँ। "
        f"{date_text} को यह हुआ:\n\n{req.description}\n\n"
        f"सबूत:\n{evidence}\n\n"
        f"कृपया 7 दिन के अंदर इसका समाधान करें{' और ' + amount_text + ' का भुगतान करें' if amount_text else ''} "
        f"और लिखित में जवाब दें। समाधान न होने पर मैं संबंधित अधिकारी के पास जाऊँगा/जाऊँगी।\n\n"
        f"धन्यवाद,\n[YOUR NAME]\nफोन: [YOUR PHONE]"
    )
    return f"{hindi}\n---\n{english}"
