"""Document help: image validation, PII masking and offline fallbacks."""

import base64
import binascii

from app.languages import offline_language
from app.schemas import Profile
from app.services import knowledge

# Leading "magic bytes" of each allowed image type. Checking content, not just the declared
# MIME type, stops other file types being smuggled through as images.
_MAGIC = {
    "image/jpeg": (b"\xff\xd8\xff",),
    "image/png": (b"\x89PNG\r\n\x1a\n",),
    "image/webp": (b"RIFF",),
}


class InvalidImageError(ValueError):
    """Raised when an uploaded image is malformed, too large or not the declared type."""


def decode_image(image_base64: str, mime_type: str, max_bytes: int) -> bytes:
    """Decode and validate a base64 image. Accepts an optional ``data:`` URL prefix."""
    payload = image_base64.split(",", 1)[1] if image_base64.startswith("data:") else image_base64
    try:
        data = base64.b64decode(payload, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise InvalidImageError("Image is not valid base64") from exc
    if not data:
        raise InvalidImageError("Image is empty")
    if len(data) > max_bytes:
        raise InvalidImageError(f"Image is larger than {max_bytes // 1_000_000} MB")
    signatures = _MAGIC.get(mime_type)
    if not signatures or not any(data.startswith(sig) for sig in signatures):
        raise InvalidImageError("File content does not match an allowed image type")
    if mime_type == "image/webp" and data[8:12] != b"WEBP":
        raise InvalidImageError("File content does not match an allowed image type")
    return data


def checklist(scheme_id: str, profile: Profile) -> dict | None:
    """Documents needed for a scheme, localized. ``None`` for an unknown scheme."""
    scheme = knowledge.scheme_by_id().get(scheme_id)
    if scheme is None:
        return None
    lang = offline_language(profile.language)
    names = knowledge.document_names()
    return {
        "scheme_id": scheme_id,
        "scheme_name": knowledge.localized(scheme["name"], lang),
        "documents": [
            {"id": doc, "name": knowledge.localized(names[doc], lang)} for doc in scheme["documents"]
        ],
        "how_to_apply": knowledge.localized(scheme["how_to_apply"], lang),
        "official_url": scheme["official_url"],
    }


def offline_document_help(lang: str) -> str:
    """Generic guidance when the AI explanation is unavailable."""
    if lang == "hi":
        return (
            "अभी AI से दस्तावेज़ समझाना उपलब्ध नहीं है। तब तक:\n"
            "- दस्तावेज़ में तारीख, रकम और 'अंतिम तिथि' वाले हिस्से ढूँढें।\n"
            "- बिना समझे किसी कागज़ पर हस्ताक्षर न करें।\n"
            "- किसी को OTP, आधार या बैंक नंबर न दें।\n"
            "- नज़दीकी CSC या ज़िला विधिक सेवा प्राधिकरण से मुफ्त मदद लें।"
        )
    return (
        "AI document explanation is unavailable right now. Meanwhile:\n"
        "- Look for dates, money amounts and any 'last date' or deadline.\n"
        "- Do not sign anything you do not understand.\n"
        "- Never share OTPs, Aadhaar or bank numbers with anyone who calls about it.\n"
        "- Get free help at a CSC or your District Legal Services Authority."
    )
