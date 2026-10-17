"""Weekly goal planner: every decision branch, safety caps and messages."""

from datetime import date, timedelta

import pytest

from app.schemas import EarningEntry
from app.services.planner import SAFE_DAY_HOURS, plan_message, plan_week

WEDNESDAY = date(2026, 10, 14)  # Monday is 12 Oct 2026
MONDAY = WEDNESDAY - timedelta(days=2)


def day(offset: int, net: float, hours: float = 8, platform: str = "Swiggy") -> EarningEntry:
    """An entry ``offset`` days after Monday with exactly ``net`` take-home."""
    return EarningEntry(day=MONDAY + timedelta(days=offset), platform=platform, gross=net, hours=hours)


def test_no_entries_means_no_data():
    plan = plan_week(5000, [], WEDNESDAY)
    assert plan.status == "no_data"
    assert plan.remaining == 5000
    assert plan.hours_needed is None
    assert "Log at least one day" in plan_message(plan, "en")


def test_goal_already_reached():
    plan = plan_week(1500, [day(0, 800), day(1, 900)], WEDNESDAY)
    assert plan.status == "achieved"
    assert plan.progress == 1.0
    assert plan.remaining == 0
    assert "Goal reached" in plan_message(plan, "en")


def test_on_track_uses_this_weeks_rate_and_counts_today_when_not_worked():
    # Mon + Tue: 1600 over 16 h = ₹100/h. Wednesday not logged yet -> 5 days left (Wed..Sun).
    plan = plan_week(5600, [day(0, 800), day(1, 800)], WEDNESDAY)
    assert plan.status == "on_track"
    assert plan.rate_per_hour == 100
    assert plan.days_left == 5
    assert plan.remaining == 4000
    assert plan.hours_needed == 40
    assert plan.hours_per_day == 8
    assert "about 40 hours" in plan_message(plan, "en")


def test_today_not_counted_once_logged():
    plan = plan_week(5600, [day(0, 800), day(1, 800), day(2, 800)], WEDNESDAY)
    assert plan.days_left == 4


def test_stretch_when_more_than_ten_hours_a_day():
    friday = MONDAY + timedelta(days=4)
    plan = plan_week(4000, [day(0, 800)], friday)  # 3200 / ₹100 = 32 h over Fri-Sun
    assert plan.status == "stretch"
    assert plan.hours_per_day == pytest.approx(10.7)
    assert "long stretch" in plan_message(plan, "en")


def test_unsafe_goal_suggests_realistic_target():
    plan = plan_week(20_000, [day(0, 800), day(1, 800)], WEDNESDAY)
    assert plan.status == "unsafe"
    # Safe hours left: min(5 days * 12 h, 60 h - 16 h worked) = 44 h at ₹100/h -> 1600 + 4400.
    assert plan.realistic_goal == 6000
    message = plan_message(plan, "en")
    assert "realistic goal" in message and "₹6,000" in message


def test_weekly_hour_cap_beats_daily_cap():
    # 50 hours already worked: only 10 safe hours remain even though 5 days are left.
    entries = [day(0, 1700, hours=17), day(1, 1700, hours=17), day(2, 1600, hours=16)]
    plan = plan_week(8000, entries, WEDNESDAY)
    assert plan.rate_per_hour == 100
    assert plan.days_left == 4  # 4 days * 12 h = 48 h, but the week allows only 10 more
    assert plan.status == "unsafe"
    assert plan.realistic_goal == 6000


def test_falls_back_to_history_rate_when_week_has_no_hours():
    last_week = [EarningEntry(day=MONDAY - timedelta(days=3), platform="Ola", gross=1200, hours=8)]
    plan = plan_week(3000, last_week, MONDAY)
    assert plan.rate_per_hour == 150
    assert plan.earned == 0
    assert plan.days_left == 7
    assert plan.status == "on_track"


def test_week_over_on_sunday_after_logging():
    sunday = MONDAY + timedelta(days=6)
    plan = plan_week(10_000, [day(6, 900)], sunday)
    assert plan.status == "week_over"
    assert "fresh plan" in plan_message(plan, "en")


def test_best_weekdays_and_platform_are_named():
    entries = [
        day(0, 600, platform="Zomato"),
        day(1, 1200, platform="Swiggy"),
        day(2, 900, platform="Swiggy"),
    ]
    plan = plan_week(9000, entries, WEDNESDAY)
    assert plan.best_weekdays == [1, 2]  # Tuesday, then Wednesday
    assert plan.best_platform == "Swiggy"
    message = plan_message(plan, "en")
    assert "Tuesday and Wednesday" in message
    assert "Swiggy pays you best" in message


def test_hindi_message():
    plan = plan_week(5600, [day(0, 800), day(1, 800)], WEDNESDAY)
    message = plan_message(plan, "hi")
    assert "घंटे" in message
    assert "सोमवार और मंगलवार" in message


def test_zero_hour_entries_never_divide_by_zero():
    plan = plan_week(3000, [day(0, 500, hours=0)], WEDNESDAY)
    assert plan.status == "no_data"
    assert plan.earned == 500


def test_safe_day_cap_is_documented_value():
    assert SAFE_DAY_HOURS == 12
