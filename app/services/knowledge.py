"""Curated knowledge base, loaded once from JSON and cached in memory."""

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def _load(name: str) -> Any:
    with (DATA_DIR / name).open(encoding="utf-8") as handle:
        return json.load(handle)


@lru_cache
def schemes() -> list[dict]:
    return _load("schemes.json")


@lru_cache
def scheme_by_id() -> dict[str, dict]:
    return {scheme["id"]: scheme for scheme in schemes()}


@lru_cache
def safety_tips() -> list[dict]:
    return _load("safety_tips.json")


@lru_cache
def helplines() -> dict:
    return _load("helplines.json")


@lru_cache
def document_names() -> dict[str, dict[str, str]]:
    return _load("documents.json")


def localized(value: dict[str, Any] | Any, lang: str) -> Any:
    """Pick ``lang`` from an ``{"en": ..., "hi": ...}`` dict, falling back to English."""
    if isinstance(value, dict) and "en" in value:
        return value.get(lang, value["en"])
    return value
