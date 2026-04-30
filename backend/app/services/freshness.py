"""Attention-lifecycle helpers — compute which zone a row belongs to.

The single mental model used across Today / ChildBoard / ChildDetail:

    FRESH     — new in last 48h OR status just changed to a closed
                state (so the parent can confirm) OR the row is a
                grade that landed in the last 48h
    ARCHIVED  — effectively closed AND has been settled for >24h
    STEADY    — everything else

Pure-Python; no DB session needed. Operates on plain dict rows so the
queries layer can wave them through without an extra round-trip.

The 48h / 24h thresholds are intentional defaults — short enough that
"fresh" stays meaningful (one weekend of work), long enough that you
don't miss something just because you went to sleep. Override per
caller via `fresh_window_hours` / `archive_hold_hours`.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any


FRESH_WINDOW_HOURS = 48
ARCHIVE_HOLD_HOURS = 24

_CLOSED_STATES = {"graded", "submitted", "done_at_home", "skipped"}


def _parse_dt(value: Any) -> datetime | None:
    """Best-effort parse for ISO timestamps surfaced as strings or
    datetimes. Returns timezone-aware UTC; naive inputs are assumed UTC."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str):
        try:
            d = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
        except Exception:
            return None
    return None


def _parse_date_only(value: Any) -> datetime | None:
    """For grade rows, due_or_date / graded_date is stored as YYYY-MM-DD.
    Treat them as midnight UTC for the freshness math — close enough."""
    if not value or not isinstance(value, str):
        return None
    try:
        d = datetime.fromisoformat(value)
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except Exception:
        return None


def attention_zone(
    row: dict[str, Any],
    *,
    now: datetime | None = None,
    fresh_window_hours: int = FRESH_WINDOW_HOURS,
    archive_hold_hours: int = ARCHIVE_HOLD_HOURS,
) -> str:
    """Compute the zone for a single assignment / grade dict.

    `row` is whatever `_item_to_dict` produces — uses these fields:
      - kind                      ('assignment' | 'grade' | 'comment' | …)
      - first_seen_at             ISO string
      - last_seen_at              ISO string
      - parent_marked_submitted_at  ISO string (when set)
      - effective_status          string
      - due_or_date               YYYY-MM-DD (used for grades)
    """
    now = now or datetime.now(tz=timezone.utc)
    fresh_threshold = now - timedelta(hours=fresh_window_hours)
    archive_threshold = now - timedelta(hours=archive_hold_hours)

    first_seen = _parse_dt(row.get("first_seen_at"))
    last_seen = _parse_dt(row.get("last_seen_at"))
    parent_submitted = _parse_dt(row.get("parent_marked_submitted_at"))
    eff = (row.get("effective_status") or "").strip()
    kind = (row.get("kind") or "").strip()

    is_closed = eff in _CLOSED_STATES

    # Grade rows: freshness from graded_date (= due_or_date for kind=grade).
    if kind == "grade":
        graded_at = _parse_date_only(row.get("due_or_date"))
        if graded_at and graded_at >= fresh_threshold:
            return "fresh"
        # Older grades fall to STEADY by default; the UI may still want
        # to keep anomalous ones visible — that's a UI decision, not a
        # zone decision.
        return "steady"

    # Closed assignments — stay FRESH for the 24h grace, then ARCHIVED.
    if is_closed:
        # If we know when the parent flipped it, use that timestamp.
        # Otherwise fall back to last_seen_at (the row's "I'm still
        # here" heartbeat) which is roughly when the portal confirmed it.
        anchor = parent_submitted or last_seen or first_seen
        if anchor and anchor >= archive_threshold:
            return "fresh"
        return "archived"

    # Open assignments — FRESH if newly arrived in the planner.
    if first_seen and first_seen >= fresh_threshold:
        return "fresh"

    return "steady"


def is_fresh_grade(
    row: dict[str, Any],
    *,
    now: datetime | None = None,
    hours: int = FRESH_WINDOW_HOURS,
) -> bool:
    """True if a grade row landed within the freshness window. Used by
    the kid-header pellet logic — orthogonal to the assignment zone."""
    now = now or datetime.now(tz=timezone.utc)
    threshold = now - timedelta(hours=hours)
    if (row.get("kind") or "") != "grade":
        return False
    graded_at = _parse_date_only(row.get("due_or_date"))
    return bool(graded_at and graded_at >= threshold)


def grade_pellet_tone(pct: float | None, anomalous: bool = False) -> str:
    """Pellet color: red for anomalous OR low, amber for mid, green for high.
    Mirrors the chip palette used elsewhere."""
    if anomalous:
        return "red"
    if pct is None:
        return "gray"
    if pct >= 85:
        return "green"
    if pct >= 70:
        return "amber"
    return "red"
