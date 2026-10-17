import re

from app.schemas import Profile
from app.services.eligibility import match_schemes, offline_scheme_explanation, scheme_facts


def _status(profile: Profile) -> dict[str, str]:
    return {m.id: m.status for m in match_schemes(profile)}


def test_young_low_income_delivery_worker(profile):
    status = _status(profile)
    assert status["eshram"] == "eligible"
    assert status["pm_sym"] == "eligible"
    assert status["pmsby"] == "eligible"
    assert status["pmjay_platform"] == "next_step"  # needs e-Shram first


def test_eshram_registration_unlocks_health_cover(profile):
    registered = profile.model_copy(update={"eshram_registered": True})
    assert _status(registered)["pmjay_platform"] == "eligible"
    match = scheme_facts("pmjay_platform", profile)
    assert match.next_step == "scheme:eshram"


def test_age_and_income_limits(profile):
    older = profile.model_copy(update={"age": 45, "monthly_income": 20000})
    status = _status(older)
    assert status["pm_sym"] == "not_eligible"
    assert status["pmjjby"] == "eligible"  # up to 50
    reasons = scheme_facts("pm_sym", older).reasons
    assert any("40" in r for r in reasons) and any("15000" in r for r in reasons)


def test_epfo_members_and_taxpayers_excluded(profile):
    status = _status(profile.model_copy(update={"has_epfo_or_esic": True, "pays_income_tax": True}))
    assert status["eshram"] == "not_eligible"
    assert status["pm_sym"] == "not_eligible"


def test_state_laws_only_in_their_state(profile):
    assert _status(profile)["karnataka_gig_law"] == "not_eligible"
    assert _status(profile.model_copy(update={"state": "Karnataka"}))["karnataka_gig_law"] == "eligible"


def test_platform_only_rules_exclude_domestic_workers(profile):
    domestic = profile.model_copy(update={"work_type": "domestic"})
    assert _status(domestic)["pmjay_platform"] == "not_eligible"


def test_missing_age_is_a_fixable_step(profile):
    unknown = profile.model_copy(update={"age": None})
    assert _status(unknown)["pmsby"] == "next_step"


def test_no_bank_account_points_to_jan_dhan(profile):
    match = scheme_facts("pmsby", profile.model_copy(update={"has_bank_account": False}))
    assert match.status == "next_step"
    assert any("Jan Dhan" in r for r in match.reasons)


def test_results_sorted_and_localized(profile):
    matches = match_schemes(profile.model_copy(update={"language": "hi"}))
    order = [m.status for m in matches]
    assert order == sorted(order, key=["eligible", "next_step", "not_eligible"].index)
    assert re.search("[\u0900-\u097f]", matches[0].name)  # Devanagari script


def test_unknown_scheme_returns_none(profile):
    assert scheme_facts("does_not_exist", profile) is None


def test_offline_explanation_lists_documents(profile):
    text = offline_scheme_explanation(scheme_facts("pm_sym", profile), "en")
    assert "Aadhaar" in text and "₹3,000" in text
