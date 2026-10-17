from datetime import date

from app.schemas import EarningEntry
from app.services.context_engine import build_cards
from app.services.intent import classify
from app.services.safety import select_tips
from tests.conftest import make_entries

TODAY = date(2026, 10, 17)


# --- safety -------------------------------------------------------------------------------


def test_night_tips_come_first_for_riders(profile):
    ids = [tip.id for tip in select_tips(profile, hour=23, conditions=[])]
    assert ids[0] in {"share_trip", "night_visibility", "fatigue", "unsafe_drop"}


def test_heat_condition_promotes_heat_tip(profile):
    tips = select_tips(profile, hour=14, conditions=["heat"])
    assert tips[0].id == "heat"


def test_construction_worker_gets_site_tips_not_helmet_riding(profile):
    worker = profile.model_copy(update={"work_type": "construction"})
    ids = {tip.id for tip in select_tips(worker, hour=10, conditions=[], limit=10)}
    assert "site_safety" in ids
    assert "no_phone_riding" not in ids


def test_safety_tips_localized(profile):
    tip = select_tips(profile.model_copy(update={"language": "hi"}), 14, ["rain"])[0]
    assert "बारिश" in tip.text


# --- intent -------------------------------------------------------------------------------


def test_intent_routing_english_and_hindi():
    assert classify("How much did I earn per hour this week?").name == "earnings"
    assert classify("Is it safe to ride at night in rain?").name == "safety"
    assert classify("Which pension scheme can I get?").name == "schemes"
    assert classify("Please explain this notice").name == "documents"
    assert classify("मेरी आईडी ब्लॉक हो गई, शिकायत कैसे करूँ").name == "grievance"
    assert classify("mujhe sarkari yojana batao").name == "schemes"


def test_dispute_wins_over_earnings_words():
    assert classify("My payout was not paid for last week").name == "grievance"


def test_unrelated_message_is_general():
    assert classify("hello").name == "general"


# --- context engine -----------------------------------------------------------------------


def test_new_worker_sees_onboarding_cards(profile):
    ids = [card.id for card in build_cards(profile, hour=11, entries=[])]
    assert "eshram" in ids and "track" in ids
    assert len(ids) <= 5


def test_night_rider_sees_safety_first(profile):
    cards = build_cards(profile, hour=23, entries=[])
    assert cards[0].id == "night_safety"


def test_pay_drop_card_opens_grievance(profile):
    cards = build_cards(profile, hour=11, entries=make_entries(150, 90, TODAY))
    pay_drop = next(card for card in cards if card.id == "pay_drop")
    assert pay_drop.module == "grievance"
    assert pay_drop.params["issue_type"] == "incentive_not_paid"


def test_deduction_card_carries_amount(profile):
    entries = [EarningEntry(day=TODAY, gross=1000, hours=8, platform_deductions=400)]
    card = next(c for c in build_cards(profile, 11, entries) if c.id == "high_deductions")
    assert card.params == {"issue_type": "wrong_deduction", "amount": 400}


def test_registered_worker_not_nagged_about_eshram(profile):
    registered = profile.model_copy(update={"eshram_registered": True})
    assert "eshram" not in [card.id for card in build_cards(registered, 11, [])]


# --- multi-intent routing and the assistant ------------------------------------------------


def test_rank_intents_returns_both_topics_strongest_first():
    from app.services.intent import rank_intents

    ranked = [i.name for i in rank_intents("payout late and my account is blocked, kya karu")]
    assert ranked[0] == "grievance"
    assert "earnings" in ranked
    assert rank_intents("hello there") == []


def test_every_home_card_explains_itself_in_hindi():
    from app.schemas import Profile
    from app.services.context_engine import build_cards

    cards = build_cards(Profile(language="hi", state="Delhi"), hour=22, entries=[])
    assert cards and all(card.reason for card in cards)
    assert any("रात" in card.reason for card in cards)


def test_assistant_documents_and_hindi_general_answers():
    from app.schemas import ChatRequest, Profile
    from app.services.assistant import build_context

    docs = build_context(ChatRequest(message="explain this notice letter", profile=Profile()))
    assert docs.intents == ["documents"]
    assert "Documents" in docs.offline_text

    general = build_context(ChatRequest(message="नमस्ते", profile=Profile(language="hi")))
    assert general.intents == ["general"]
    assert "अभी आपके लिए ज़रूरी" in general.offline_text
    assert general.suggested_modules  # points to the top priority card


def test_assistant_schemes_answer_lists_eligible_schemes():
    from app.schemas import ChatRequest, Profile
    from app.services.assistant import build_context

    profile = Profile(age=30, monthly_income=12000, state="Punjab", has_bank_account=True)
    context = build_context(ChatRequest(message="which government scheme can I get?", profile=profile))
    assert context.intents[0] == "schemes"
    assert "qualify" in context.offline_text or "One step away" in context.offline_text
    assert context.facts["schemes"]
