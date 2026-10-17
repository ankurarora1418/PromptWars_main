"""Static checks on the frontend: translations, accessibility basics and CSP compliance."""

import json
import re
from html.parser import HTMLParser
from pathlib import Path

STATIC = Path(__file__).resolve().parent.parent / "static"
HTML = (STATIC / "index.html").read_text(encoding="utf-8")


def load(lang: str) -> dict:
    return json.loads((STATIC / "i18n" / f"{lang}.json").read_text(encoding="utf-8"))


class Collector(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.tags: list[tuple[str, dict]] = []

    def handle_starttag(self, tag, attrs):
        self.tags.append((tag, dict(attrs)))


def parsed() -> list[tuple[str, dict]]:
    collector = Collector()
    collector.feed(HTML)
    return collector.tags


def test_english_and_hindi_have_identical_keys():
    assert set(load("en")) == set(load("hi"))


def test_every_html_i18n_key_is_translated():
    keys = set(re.findall(r'data-i18n(?:-label|-placeholder)?="([^"]+)"', HTML))
    missing = keys - set(load("en"))
    assert not missing, missing


def test_every_js_translation_key_exists():
    english = set(load("en"))
    used: set[str] = set()
    for script in (STATIC / "js").rglob("*.js"):
        used |= set(re.findall(r'\bt\("([A-Za-z]+)"', script.read_text(encoding="utf-8")))
    missing = used - english
    assert not missing, missing


def test_no_inline_script_or_style_so_strict_csp_holds():
    for tag, attrs in parsed():
        assert "style" not in attrs, f"inline style on <{tag}>"
        assert not any(name.startswith("on") for name in attrs), f"inline handler on <{tag}>"
        if tag == "script":
            assert attrs.get("src"), "inline <script> would be blocked by CSP"


def test_form_controls_have_labels():
    tags = parsed()
    label_targets = {attrs["for"] for tag, attrs in tags if tag == "label" and "for" in attrs}
    for tag, attrs in tags:
        if tag in {"input", "select", "textarea"} and attrs.get("type") not in {"checkbox", "hidden"}:
            assert attrs.get("id") in label_targets or attrs.get("aria-label"), f"unlabelled {tag} {attrs}"


def test_page_landmarks_and_language():
    tags = parsed()
    names = [tag for tag, _ in tags]
    assert {"header", "main", "nav"} <= set(names)
    assert ("html", {"lang": "en"}) in tags
    assert any(attrs.get("class") == "skip-link" for _, attrs in tags)
    assert sum(1 for tag in names if tag == "h1") == 6  # one heading per view
