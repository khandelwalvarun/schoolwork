"""Canonical time helpers. EVERY 'today' / 'due' / 'overdue' decision and
every user-visible date string must route through here. Storage stays UTC;
logic and display live in IST.

Don't use `date.today()` or `datetime.now()` (without tz) or
`.astimezone()` with no arg anywhere else in the backend — those all
quietly pick up the SYSTEM local zone, which may not be IST in prod.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")
UTC = timezone.utc


def now_ist() -> datetime:
    """Current instant as a tz-aware datetime in IST."""
    return datetime.now(tz=IST)


def now_utc() -> datetime:
    """Current instant as a tz-aware datetime in UTC (for DB columns)."""
    return datetime.now(tz=UTC)


def today_ist() -> date:
    return now_ist().date()


def today_iso_ist() -> str:
    return today_ist().isoformat()


def to_ist(dt: datetime | None) -> datetime | None:
    """Convert an aware datetime (any zone) to IST. Naive inputs are
    assumed UTC (our storage convention)."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(IST)
