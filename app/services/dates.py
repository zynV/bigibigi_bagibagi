"""Local Warsaw calendar boundaries converted to UTC for database filtering."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

WARSAW = ZoneInfo("Europe/Warsaw")
MONTH_NAMES = (
    "Січень", "Лютий", "Березень", "Квітень", "Травень", "Червень",
    "Липень", "Серпень", "Вересень", "Жовтень", "Листопад", "Грудень",
)


def iso_utc(value: datetime) -> str:
    if value.tzinfo is None:
        raise ValueError("Datetime must be timezone aware")
    return value.astimezone(timezone.utc).isoformat(timespec="microseconds")


def current_month(now: datetime | None = None) -> tuple[int, int]:
    local = (now or datetime.now(timezone.utc)).astimezone(WARSAW)
    return local.year, local.month


def shift_month(year: int, month: int, offset: int) -> tuple[int, int]:
    datetime(year, month, 1)  # Validate the starting calendar month.
    index = (year - 1) * 12 + month - 1 + offset
    if not 0 <= index < 9999 * 12:
        raise ValueError("Month is outside the supported calendar")
    new_year, new_month = divmod(index, 12)
    return new_year + 1, new_month + 1


def month_bounds(year: int, month: int) -> tuple[str, str]:
    start = datetime(year, month, 1, tzinfo=WARSAW)
    next_year, next_month = shift_month(year, month, 1)
    end = datetime(next_year, next_month, 1, tzinfo=WARSAW)
    return iso_utc(start), iso_utc(end)


def month_label(year: int, month: int) -> str:
    datetime(year, month, 1)
    return f"{MONTH_NAMES[month - 1]} {year}"


def period_bounds(period: str, now: datetime | None = None) -> tuple[str, str]:
    current = (now or datetime.now(timezone.utc)).astimezone(WARSAW)
    midnight = current.replace(hour=0, minute=0, second=0, microsecond=0)
    if period == "today":
        start, end = midnight, midnight + timedelta(days=1)
    elif period == "week":
        start = midnight - timedelta(days=current.weekday())
        end = start + timedelta(days=7)
    elif period == "month":
        return month_bounds(current.year, current.month)
    else:
        raise ValueError(f"Unknown period: {period}")
    return iso_utc(start), iso_utc(end)
