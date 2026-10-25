"""Local Warsaw calendar boundaries converted to UTC for database filtering."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

WARSAW = ZoneInfo("Europe/Warsaw")


def iso_utc(value: datetime) -> str:
    if value.tzinfo is None:
        raise ValueError("Datetime must be timezone aware")
    return value.astimezone(timezone.utc).isoformat(timespec="microseconds")


def period_bounds(period: str, now: datetime | None = None) -> tuple[str, str]:
    current = (now or datetime.now(timezone.utc)).astimezone(WARSAW)
    midnight = current.replace(hour=0, minute=0, second=0, microsecond=0)
    if period == "today":
        start, end = midnight, midnight + timedelta(days=1)
    elif period == "week":
        start = midnight - timedelta(days=current.weekday())
        end = start + timedelta(days=7)
    elif period == "month":
        start = midnight.replace(day=1)
        if start.month == 12:
            end = start.replace(year=start.year + 1, month=1)
        else:
            end = start.replace(month=start.month + 1)
    else:
        raise ValueError(f"Unknown period: {period}")
    return iso_utc(start), iso_utc(end)
