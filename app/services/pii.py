"""Mask personal identifiers before any text leaves the server for the LLM.

Workers often paste notices or contracts containing Aadhaar, PAN, phone or card numbers.
None of that is needed to explain a document, so it is replaced with placeholders.
"""

import re
from dataclasses import dataclass, field

# Order matters: longer / more specific patterns run first so a card number is not
# half-matched as an Aadhaar number.
_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("EMAIL", re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")),
    ("UPI_ID", re.compile(r"\b[\w.-]{2,}@(?:ok[a-z]+|ybl|ibl|axl|upi|paytm|apl|[a-z]{2,10}bank)\b", re.I)),
    ("CARD", re.compile(r"\b(?:\d[ -]?){15,18}\d\b")),
    ("AADHAAR", re.compile(r"\b[2-9]\d{3}[ -]?\d{4}[ -]?\d{4}\b")),
    ("PAN", re.compile(r"\b[A-Z]{5}\d{4}[A-Z]\b")),
    ("PHONE", re.compile(r"(?<!\d)(?:\+?91[ -]?|0)?[6-9]\d{4}[ -]?\d{5}(?!\d)")),
    ("ACCOUNT", re.compile(r"(?i)\b(?:a/?c|account)\s*(?:no\.?|number)?\s*[:#-]?\s*\d{9,18}\b")),
]


@dataclass(frozen=True)
class MaskResult:
    """Masked text plus a count of what was hidden, by category."""

    text: str
    found: dict[str, int] = field(default_factory=dict)

    @property
    def masked_anything(self) -> bool:
        return bool(self.found)


def mask_pii(text: str) -> MaskResult:
    """Replace personal identifiers in ``text`` with ``[LABEL]`` placeholders."""
    found: dict[str, int] = {}
    masked = text
    # UPI handles must be masked before the generic email rule swallows them.
    ordered = sorted(_PATTERNS, key=lambda item: item[0] != "UPI_ID")
    for label, pattern in ordered:
        masked, count = pattern.subn(f"[{label}]", masked)
        if count:
            found[label] = found.get(label, 0) + count
    return MaskResult(text=masked, found=found)
