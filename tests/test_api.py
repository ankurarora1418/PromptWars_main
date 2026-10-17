"""End-to-end API tests using a fake Gemini client (no network)."""

import base64
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from tests.conftest import FakeAI

TODAY = date.today()
PROFILE = {"language": "en", "work_type": "delivery", "state": "Punjab", "age": 28, "monthly_income": 14000}
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


def make_client(ai: FakeAI | None = None, **settings) -> tuple[TestClient, FakeAI]:
    ai = ai or FakeAI()
    app = create_app(Settings(gemini_api_key=None, rate_limit_per_minute=1000, **settings), ai_client=ai)
    return TestClient(app), ai


@pytest.fixture
def client() -> TestClient:
    return make_client()[0]


def week_entries() -> list[dict]:
    return [
        {"day": (TODAY - timedelta(days=i)).isoformat(), "platform": "Zomato", "gross": 1000,
         "hours": 8, "fuel_cost": 150, "platform_deductions": 50}
        for i in range(5)
    ]  # fmt: skip


# --- core ---------------------------------------------------------------------------------


def test_health_never_exposes_key(client):
    body = client.get("/api/health").json()
    assert body["status"] == "ok"
    assert "key" not in str(body).lower()


def test_meta_lists_languages_states_and_issue_types(client):
    body = client.get("/api/meta?lang=hi").json()
    assert {"en", "hi", "ta"} <= {lang["code"] for lang in body["languages"]}
    assert "Punjab" in body["states"]
    assert any(item["id"] == "deactivation" for item in body["issue_types"])


def test_index_served_with_security_headers(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "default-src 'self'" in response.headers["content-security-policy"]
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["x-content-type-options"] == "nosniff"


def test_home_cards(client):
    body = client.post("/api/home", json={"profile": PROFILE, "hour": 23}).json()
    assert body["cards"][0]["id"] == "night_safety"
    assert all({"title", "body", "module"} <= set(card) for card in body["cards"])


def test_chat_routes_intent_and_masks_pii():
    client, ai = make_client()
    body = client.post(
        "/api/chat", json={"profile": PROFILE, "message": "My ID is blocked, my phone is 9876543210"}
    ).json()
    assert body["intent"] == "grievance"
    assert body["answer"]["source"] == "gemini"
    assert "9876543210" not in ai.prompts[-1]


def test_chat_offline_fallback():
    client, _ = make_client(FakeAI(enabled=False))
    body = client.post("/api/chat", json={"profile": PROFILE, "message": "hello"}).json()
    assert body["intent"] == "general"
    assert body["answer"]["source"] == "offline"
    assert "Earnings" in body["answer"]["text"]


# --- earnings -----------------------------------------------------------------------------


def test_earnings_summary_numbers_and_explanation():
    client, ai = make_client()
    body = client.post("/api/earnings/summary", json={"profile": PROFILE, "entries": week_entries()}).json()
    assert body["summary"]["net_earnings"] == 4000  # 5 x (1000 - 150 - 50)
    assert body["summary"]["net_per_hour"] == 100
    assert body["explanation"]["source"] == "gemini"
    assert '"net_earnings": 4000' in ai.prompts[-1]


def test_earnings_without_entries_skips_ai():
    client, ai = make_client()
    body = client.post("/api/earnings/summary", json={"profile": PROFILE, "entries": []}).json()
    assert body["explanation"] is None
    assert ai.prompts == []


def test_earnings_rejects_negative_and_absurd_values(client):
    bad = week_entries()
    bad[0]["gross"] = -5
    assert client.post("/api/earnings/summary", json={"profile": PROFILE, "entries": bad}).status_code == 422
    bad[0]["gross"] = 100
    bad[0]["hours"] = 30
    assert client.post("/api/earnings/summary", json={"profile": PROFILE, "entries": bad}).status_code == 422


# --- safety / schemes ---------------------------------------------------------------------


def test_safety_tips_without_question_do_not_call_ai():
    client, ai = make_client()
    body = client.post("/api/safety", json={"profile": PROFILE, "hour": 14, "conditions": ["heat"]}).json()
    assert body["tips"][0]["id"] == "heat"
    assert body["answer"] is None
    assert any(h["number"] == "112" for h in body["helplines"])
    assert ai.prompts == []


def test_safety_question_answered(client):
    body = client.post(
        "/api/safety", json={"profile": PROFILE, "hour": 22, "question": "Is it safe to ride now?"}
    ).json()
    assert body["answer"]["text"] == "AI reply"


def test_schemes_match_and_explain(client):
    schemes = client.post("/api/schemes/match", json={"profile": PROFILE}).json()["schemes"]
    assert {s["id"]: s["status"] for s in schemes}["pm_sym"] == "eligible"
    explained = client.post("/api/schemes/explain", json={"profile": PROFILE, "scheme_id": "pm_sym"}).json()
    assert explained["scheme"]["id"] == "pm_sym"
    assert explained["answer"]["source"] == "gemini"


def test_unknown_scheme_404_and_bad_id_422(client):
    assert (
        client.post("/api/schemes/explain", json={"profile": PROFILE, "scheme_id": "nope"}).status_code == 404
    )
    bad = client.post("/api/schemes/explain", json={"profile": PROFILE, "scheme_id": "../etc"})
    assert bad.status_code == 422


def test_checklist(client):
    body = client.post("/api/documents/checklist", json={"profile": PROFILE, "scheme_id": "eshram"}).json()
    assert body["documents"][0]["name"] == "Aadhaar card"


# --- documents ----------------------------------------------------------------------------


def test_document_text_is_masked_before_ai():
    client, ai = make_client()
    text = "Notice to Ravi, Aadhaar 2345 6789 0123, phone 9876543210. Pay Rs 500 fine by 20 Oct."
    body = client.post("/api/documents/explain", json={"profile": PROFILE, "text": text}).json()
    assert "2345 6789 0123" not in ai.prompts[-1] and "9876543210" not in ai.prompts[-1]
    assert body["masked"] == {"AADHAAR": 1, "PHONE": 1}
    assert "AADHAAR" in body["answer"]["privacy_note"]


def test_document_photo_validated_and_sent():
    client, ai = make_client()
    payload = {"profile": PROFILE, "image_base64": base64.b64encode(PNG).decode(), "image_mime": "image/png"}
    assert client.post("/api/documents/explain", json=payload).status_code == 200
    assert ai.images[-1].mime_type == "image/png"


def test_document_rejects_fake_image_and_empty_request(client):
    fake = {"profile": PROFILE, "image_base64": base64.b64encode(b"MZ-not-an-image").decode(),
            "image_mime": "image/png"}  # fmt: skip
    assert client.post("/api/documents/explain", json=fake).status_code == 422
    assert client.post("/api/documents/explain", json={"profile": PROFILE}).status_code == 422


# --- grievance ----------------------------------------------------------------------------


def grievance_payload(**overrides) -> dict:
    payload = {
        "profile": PROFILE,
        "issue_type": "wrong_deduction",
        "against": "Zomato",
        "incident_date": TODAY.isoformat(),
        "amount": 400,
        "description": "A late penalty of Rs 400 was cut though the restaurant delayed the order.",
        "evidence": ["Screenshot of order timeline", "Payout statement"],
    }
    payload.update(overrides)
    return payload


def test_grievance_draft_with_where_to_file():
    client, ai = make_client()
    body = client.post("/api/grievance/draft", json=grievance_payload()).json()
    assert body["draft"]["source"] == "gemini"
    assert body["where_to_file"]["file_with"]
    assert "[YOUR NAME]" in body["placeholders"]
    assert '"amount_rupees": 400' in ai.prompts[-1]


def test_grievance_offline_template_in_hindi():
    client, _ = make_client(FakeAI(enabled=False))
    payload = grievance_payload(profile={**PROFILE, "language": "hi"})
    draft = client.post("/api/grievance/draft", json=payload).json()["draft"]
    assert draft["source"] == "offline"
    assert "शिकायत" in draft["text"] and "Complaint" in draft["text"]
    assert "[YOUR NAME]" in draft["text"]


def test_grievance_rejects_future_date_and_unknown_type(client):
    future = (TODAY + timedelta(days=3)).isoformat()
    assert (
        client.post("/api/grievance/draft", json=grievance_payload(incident_date=future)).status_code == 422
    )
    assert client.post("/api/grievance/draft", json=grievance_payload(issue_type="x")).status_code == 422


def test_harassment_lists_emergency_numbers(client):
    body = client.post("/api/grievance/draft", json=grievance_payload(issue_type="harassment")).json()
    assert {"112", "181"} <= {h["number"] for h in body["where_to_file"]["helplines"]}


# --- input validation & abuse protection --------------------------------------------------


def test_unknown_fields_and_bad_state_rejected(client):
    assert client.post("/api/home", json={"profile": PROFILE, "admin": True}).status_code == 422
    bad_state = {**PROFILE, "state": "Atlantis"}
    response = client.post("/api/schemes/match", json={"profile": bad_state})
    assert response.status_code == 422
    assert "Atlantis" not in response.text  # submitted values are not echoed back


def test_oversized_body_rejected(client):
    response = client.post(
        "/api/chat", content=b"x", headers={"content-length": "9000000", "content-type": "application/json"}
    )
    assert response.status_code == 413


def test_rate_limit_returns_429():
    app = create_app(Settings(gemini_api_key=None, rate_limit_per_minute=2), ai_client=FakeAI())
    client = TestClient(app)
    codes = [client.post("/api/home", json={"profile": PROFILE}).status_code for _ in range(3)]
    assert codes == [200, 200, 429]
    assert client.get("/api/health").status_code == 200  # GETs are not limited


def test_api_responses_not_cached(client):
    assert client.get("/api/health").headers["cache-control"] == "no-store"
