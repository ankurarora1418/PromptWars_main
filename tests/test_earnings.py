from datetime import date

import pytest

from app.schemas import EarningEntry
from app.services.earnings import alert_message, offline_explanation, summarize
from tests.conftest import make_entries

TODAY = date(2026, 10, 17)


def test_empty_entries_give_empty_summary():
    summary = summarize([])
    assert summary.days_worked == 0
    assert summary.alerts == []
    assert "No earnings" in offline_explanation(summary, "en")


def test_net_and_rates_are_exact():
    entries = [
        EarningEntry(
            day=TODAY,
            platform="Zomato",
            gross=1200,
            tips=50,
            hours=8,
            km=80,
            fuel_cost=200,
            other_expenses=50,
            platform_deductions=100,
        ),
    ]
    summary = summarize(entries)
    assert summary.net_earnings == 900  # 1200 + 50 - 100 - 200 - 50
    assert summary.net_per_hour == 112.5
    assert summary.net_per_km == 11.25
    assert summary.expense_share == pytest.approx(0.2)
    assert summary.deduction_share == pytest.approx(0.08)


def test_zero_hours_does_not_divide_by_zero():
    summary = summarize([EarningEntry(day=TODAY, gross=500, hours=0)])
    assert summary.net_per_hour is None


def test_pay_drop_alert_links_to_grievance():
    summary = summarize(make_entries(150, 100, TODAY), today=TODAY)
    codes = {alert.code: alert for alert in summary.alerts}
    assert "pay_drop" in codes
    assert codes["pay_drop"].action == "grievance:incentive_not_paid"
    assert codes["pay_drop"].data["drop_pct"] == 33


def test_small_dip_is_not_flagged():
    summary = summarize(make_entries(150, 140, TODAY), today=TODAY)
    assert all(alert.code != "pay_drop" for alert in summary.alerts)


def test_high_deductions_and_long_hours_flagged():
    entries = [EarningEntry(day=TODAY, gross=1000, hours=13, platform_deductions=300)]
    codes = {alert.code for alert in summarize(entries).alerts}
    assert {"high_deductions", "long_hours"} <= codes


def test_best_platform_picked_by_hourly_rate():
    entries = [
        EarningEntry(day=TODAY, platform="A", gross=800, hours=8),
        EarningEntry(day=TODAY, platform="B", gross=600, hours=4),
    ]
    summary = summarize(entries)
    assert summary.best_platform == "B"
    assert summary.days_worked == 1


def test_alert_text_available_in_hindi():
    summary = summarize(make_entries(150, 100, TODAY), today=TODAY)
    pay_drop = next(a for a in summary.alerts if a.code == "pay_drop")
    assert "हफ्ते" in alert_message(pay_drop, "hi")
    assert "₹" in offline_explanation(summary, "hi")
