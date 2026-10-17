import base64

import pytest

from app.security import RateLimiter
from app.services.documents import InvalidImageError, decode_image

JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 32
WEBP = b"RIFF\x00\x00\x00\x00WEBPVP8 " + b"\x00" * 16


def test_rate_limiter_window_slides():
    limiter = RateLimiter(limit=2, window=60)
    assert limiter.allow("ip", now=0)[0]
    assert limiter.allow("ip", now=1)[0]
    allowed, retry = limiter.allow("ip", now=2)
    assert not allowed and retry > 0
    assert limiter.allow("ip", now=61)[0]  # first hit expired
    assert limiter.allow("other", now=2)[0]  # separate key


def test_rate_limiter_bounded_memory():
    limiter = RateLimiter(limit=1, window=60, max_keys=10)
    for i in range(50):
        limiter.allow(f"ip{i}", now=float(i))
    assert len(limiter._hits) <= 10


def test_decode_valid_images_including_data_url():
    assert decode_image(base64.b64encode(JPEG).decode(), "image/jpeg", 1_000) == JPEG
    data_url = "data:image/webp;base64," + base64.b64encode(WEBP).decode()
    assert decode_image(data_url, "image/webp", 1_000) == WEBP


@pytest.mark.parametrize(
    ("payload", "mime"),
    [
        ("not base64!!", "image/jpeg"),
        (base64.b64encode(JPEG).decode(), "image/png"),  # declared type does not match bytes
        (base64.b64encode(b"RIFF\x00\x00\x00\x00WAVE").decode(), "image/webp"),
        ("", "image/jpeg"),
    ],
)
def test_decode_rejects_bad_images(payload, mime):
    with pytest.raises(InvalidImageError):
        decode_image(payload, mime, 1_000)


def test_decode_rejects_oversized_image():
    with pytest.raises(InvalidImageError):
        decode_image(base64.b64encode(JPEG * 100).decode(), "image/jpeg", 100)


# --- pure ASGI middleware and memoisation -----------------------------------------------------


def test_client_ip_uses_first_forwarded_hop_only_when_trusted():
    from app.security import client_ip

    scope = {
        "type": "http",
        "headers": [(b"x-forwarded-for", b"203.0.113.9, 10.0.0.1")],
        "client": ("10.0.0.1", 1),
    }
    assert client_ip(scope, trust_proxy=True) == "203.0.113.9"
    assert client_ip(scope, trust_proxy=False) == "10.0.0.1"
    assert client_ip({"type": "http", "headers": []}, trust_proxy=False) == "unknown"


def test_invalid_content_length_is_rejected_and_static_files_are_cacheable():
    from fastapi.testclient import TestClient

    from app.config import Settings
    from app.main import create_app
    from tests.conftest import FakeAI

    client = TestClient(create_app(Settings(gemini_api_key=None), ai_client=FakeAI()))
    bad = client.post(
        "/api/chat", content=b"{}", headers={"content-length": "abc", "content-type": "application/json"}
    )
    assert bad.status_code == 400
    static = client.get("/static/css/styles.css")
    assert static.status_code == 200
    assert "max-age=86400" in static.headers["cache-control"]
    assert static.headers["x-content-type-options"] == "nosniff"


def test_scheme_matching_is_memoised_per_profile():
    from app.schemas import Profile
    from app.services import eligibility

    eligibility._match_schemes.cache_clear()
    profile = Profile(age=30, monthly_income=12000, state="Punjab")
    first = eligibility.match_schemes(profile)
    second = eligibility.match_schemes(Profile(age=30, monthly_income=12000, state="Punjab"))
    assert first == second
    assert eligibility._match_schemes.cache_info().hits == 1
    first.clear()  # callers get their own list; the cached result is untouched
    assert eligibility.match_schemes(profile)


def test_build_cards_reuses_a_precomputed_summary():
    from app.schemas import Profile
    from app.services.context_engine import build_cards
    from app.services.earnings import summarize

    summary = summarize([])
    cards = build_cards(Profile(), hour=10, entries=[], summary=summary)
    assert [c.id for c in cards] == [c.id for c in build_cards(Profile(), hour=10, entries=[])]
