"""Supported languages.

The UI chrome is translated into ``UI_LANGUAGES``; Gemini can answer in every language in
``SUPPORTED_LANGUAGES``. Offline fallbacks exist in English and Hindi.
"""

from typing import Literal

LanguageCode = Literal["en", "hi", "pa", "ta", "te", "bn", "mr", "kn"]

SUPPORTED_LANGUAGES: dict[str, str] = {
    "en": "English",
    "hi": "Hindi",
    "pa": "Punjabi",
    "ta": "Tamil",
    "te": "Telugu",
    "bn": "Bengali",
    "mr": "Marathi",
    "kn": "Kannada",
}

# Native-script names shown in the language picker.
NATIVE_NAMES: dict[str, str] = {
    "en": "English",
    "hi": "हिन्दी",
    "pa": "ਪੰਜਾਬੀ",
    "ta": "தமிழ்",
    "te": "తెలుగు",
    "bn": "বাংলা",
    "mr": "मराठी",
    "kn": "ಕನ್ನಡ",
}

UI_LANGUAGES = ("en", "hi")
OFFLINE_LANGUAGES = ("en", "hi")


def offline_language(code: str) -> str:
    """Language used for template (non-AI) text: Hindi if chosen, otherwise English."""
    return code if code in OFFLINE_LANGUAGES else "en"


def language_name(code: str) -> str:
    """English name of a language code, defaulting to English."""
    return SUPPORTED_LANGUAGES.get(code, "English")
