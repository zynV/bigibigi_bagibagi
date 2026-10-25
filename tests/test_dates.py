from datetime import datetime, timezone
from zoneinfo import ZoneInfo
import pytest
from app.services.dates import period_bounds

WARSAW = ZoneInfo("Europe/Warsaw")


def test_week_monday_to_next_monday():
    now = datetime(2026, 10, 25, 13, tzinfo=WARSAW)  # Sunday
    start, end = period_bounds("week", now)
    assert datetime.fromisoformat(start).astimezone(WARSAW).date().isoformat() == "2026-10-19"
    assert datetime.fromisoformat(end).astimezone(WARSAW).date().isoformat() == "2026-10-26"


def test_dst_fall_back_is_25_hour_day():
    now = datetime(2026, 10, 25, 14, tzinfo=WARSAW)
    start, end = period_bounds("today", now)
    first = datetime.fromisoformat(start)
    second = datetime.fromisoformat(end)
    assert (second - first).total_seconds() == 25 * 3600


def test_dst_spring_forward_is_23_hour_day():
    now = datetime(2026, 3, 29, 14, tzinfo=WARSAW)
    start, end = period_bounds("today", now)
    assert (datetime.fromisoformat(end) - datetime.fromisoformat(start)).total_seconds() == 23 * 3600


def test_month_year_boundary():
    start, end = period_bounds("month", datetime(2026, 12, 27, tzinfo=WARSAW))
    assert datetime.fromisoformat(start).astimezone(WARSAW).strftime("%Y-%m-%d") == "2026-12-01"
    assert datetime.fromisoformat(end).astimezone(WARSAW).strftime("%Y-%m-%d") == "2027-01-01"


def test_unknown_period():
    with pytest.raises(ValueError):
        period_bounds("tomorrow")
