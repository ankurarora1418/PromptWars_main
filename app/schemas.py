"""Request and response models.

Every request field is typed and bounded, so oversized or malformed input is rejected with a
422 before it reaches business logic or the LLM. ``extra="forbid"`` blocks unexpected fields.
"""

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.languages import LanguageCode

WorkType = Literal["delivery", "ride_driver", "daily_wage", "domestic", "construction", "other"]
Shift = Literal["day", "night", "mixed"]
Condition = Literal["heat", "rain", "cold", "fog", "pollution"]
IssueType = Literal[
    "deactivation",
    "unpaid_earnings",
    "wrong_deduction",
    "incentive_not_paid",
    "employer_wage_theft",
    "accident_injury",
    "harassment",
    "payment_fraud",
    "other",
]
ImageMime = Literal["image/jpeg", "image/png", "image/webp"]

INDIAN_STATES = (
    "Andhra Pradesh", "Arunachal Pradesh", "Assam", "Bihar", "Chhattisgarh", "Goa", "Gujarat",
    "Haryana", "Himachal Pradesh", "Jharkhand", "Karnataka", "Kerala", "Madhya Pradesh",
    "Maharashtra", "Manipur", "Meghalaya", "Mizoram", "Nagaland", "Odisha", "Punjab",
    "Rajasthan", "Sikkim", "Tamil Nadu", "Telangana", "Tripura", "Uttar Pradesh",
    "Uttarakhand", "West Bengal", "Andaman and Nicobar Islands", "Chandigarh",
    "Dadra and Nagar Haveli and Daman and Diu", "Delhi", "Jammu and Kashmir", "Ladakh",
    "Lakshadweep", "Puducherry",
)  # fmt: skip


class StrictModel(BaseModel):
    """Base model: strip whitespace, reject unknown fields."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Profile(StrictModel):
    """Worker context. Kept on the worker's device; sent with each request, never stored."""

    language: LanguageCode = "en"
    work_type: WorkType = "delivery"
    state: str = Field(default="Delhi", max_length=60)
    age: int | None = Field(default=None, ge=14, le=100)
    monthly_income: int | None = Field(default=None, ge=0, le=1_000_000)
    shift: Shift = "day"
    has_epfo_or_esic: bool = False
    pays_income_tax: bool = False
    eshram_registered: bool = False
    has_bank_account: bool = True

    @field_validator("state")
    @classmethod
    def _known_state(cls, value: str) -> str:
        if value not in INDIAN_STATES:
            raise ValueError("Unknown state or union territory")
        return value


class EarningEntry(StrictModel):
    """One day of work on one platform (or one employer)."""

    day: date
    platform: str = Field(default="Other", min_length=1, max_length=40)
    gross: float = Field(ge=0, le=100_000)
    tips: float = Field(default=0, ge=0, le=50_000)
    hours: float = Field(ge=0, le=24)
    km: float = Field(default=0, ge=0, le=1_500)
    fuel_cost: float = Field(default=0, ge=0, le=50_000)
    other_expenses: float = Field(default=0, ge=0, le=50_000)
    platform_deductions: float = Field(default=0, ge=0, le=100_000)


class EarningsRequest(StrictModel):
    profile: Profile = Field(default_factory=Profile)
    entries: list[EarningEntry] = Field(default_factory=list, max_length=400)
    question: str | None = Field(default=None, max_length=500)


class SafetyRequest(StrictModel):
    profile: Profile = Field(default_factory=Profile)
    hour: int = Field(default=12, ge=0, le=23)
    conditions: list[Condition] = Field(default_factory=list, max_length=5)
    question: str | None = Field(default=None, max_length=500)


class SchemesRequest(StrictModel):
    profile: Profile = Field(default_factory=Profile)


class SchemeExplainRequest(StrictModel):
    profile: Profile = Field(default_factory=Profile)
    scheme_id: str = Field(min_length=2, max_length=40, pattern=r"^[a-z0-9_]+$")
    question: str | None = Field(default=None, max_length=500)


class DocumentRequest(StrictModel):
    profile: Profile = Field(default_factory=Profile)
    text: str | None = Field(default=None, max_length=4000)
    image_base64: str | None = Field(default=None, max_length=6_000_000)
    image_mime: ImageMime | None = None
    question: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def _needs_content(self) -> "DocumentRequest":
        if not (self.text and self.text.strip()) and not self.image_base64:
            raise ValueError("Provide document text or a photo")
        if self.image_base64 and not self.image_mime:
            raise ValueError("image_mime is required with image_base64")
        return self


class GrievanceRequest(StrictModel):
    profile: Profile = Field(default_factory=Profile)
    issue_type: IssueType
    against: str = Field(min_length=1, max_length=80)  # platform, employer or contractor
    incident_date: date | None = None
    amount: float | None = Field(default=None, ge=0, le=10_000_000)
    description: str = Field(min_length=10, max_length=2000)
    evidence: list[str] = Field(default_factory=list, max_length=10)

    @field_validator("evidence")
    @classmethod
    def _short_evidence(cls, items: list[str]) -> list[str]:
        cleaned = [item.strip()[:200] for item in items if item and item.strip()]
        return cleaned

    @field_validator("incident_date")
    @classmethod
    def _not_future(cls, value: date | None) -> date | None:
        if value and value > date.today():
            raise ValueError("Incident date cannot be in the future")
        return value


class ChatRequest(StrictModel):
    profile: Profile = Field(default_factory=Profile)
    message: str = Field(min_length=1, max_length=1000)
    entries: list[EarningEntry] = Field(default_factory=list, max_length=400)


class HomeRequest(StrictModel):
    profile: Profile = Field(default_factory=Profile)
    hour: int = Field(default=12, ge=0, le=23)
    entries: list[EarningEntry] = Field(default_factory=list, max_length=400)


Source = Literal["gemini", "offline"]


class AIAnswer(BaseModel):
    """Common shape for every AI-generated answer."""

    text: str
    source: Source
    language: str
    privacy_note: str | None = None
