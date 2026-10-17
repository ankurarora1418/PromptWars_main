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
