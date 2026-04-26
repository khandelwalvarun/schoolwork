"""Excellence-Award tracker for Vasant Valley School.

The school awards an "Excellence" badge to students who maintain an
overall academic average of **85 % or higher across five consecutive
academic years**. This module computes the parent's-eye-view of how
the kid is tracking against that bar:

    current_year_avg     average % across all grades in the current
                         academic year window (April N → March N+1)
    on_track             True iff current_year_avg ≥ 85 %
    grades_count         number of graded items in the year
    above_85_count       number of those at ≥ 85 %
    above_85_share       above_85_count / grades_count (proportion)
    below_85_recent      ids of the most-recent <85% graded items
                         (so the parent can drill into where slippage
                         happened)

The "five years" check is intentionally NOT computed here — the
cockpit only has the current year of data scraped, so showing the
streak would be dishonest. We surface ONE year's status; the parent
tracks year-over-year themselves until we have multi-year scrape data.

Returns the same shape per kid; aggregator builds it for both kids.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Child, VeracrossItem
from .grade_match import _parse_loose_date
from ..util.time import today_ist


EXCELLENCE_THRESHOLD = 85.0


@dataclass
class ExcellenceStatus:
    child_id: int
    year_label: str
    year_start: str
    year_end: str
    grades_count: int
    above_85_count: int
    current_year_avg: float | None
    on_track: bool
    above_85_share: float
    below_85_recent: list[dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        return {
            "child_id": self.child_id,
            "year_label": self.year_label,
            "year_start": self.year_start,
            "year_end": self.year_end,
            "grades_count": self.grades_count,
            "above_85_count": self.above_85_count,
            "current_year_avg": self.current_year_avg,
            "on_track": self.on_track,
            "above_85_share": self.above_85_share,
            "below_85_recent": self.below_85_recent,
            "threshold": EXCELLENCE_THRESHOLD,
        }


def _academic_year_window(today: date) -> tuple[date, date, str]:
    """Indian academic year runs April → March. Returns (start, end, label).
    label: '2026-27' for April 2026 to March 2027."""
    if today.month >= 4:  # Apr-Dec
        y = today.year
    else:                 # Jan-Mar
        y = today.year - 1
    start = date(y, 4, 1)
    end = date(y + 1, 3, 31)
    return (start, end, f"{y}-{(y + 1) % 100:02d}")


def _grade_pct(item: VeracrossItem) -> float | None:
    if not item.normalized_json:
        return None
    try:
        v = json.loads(item.normalized_json).get("grade_pct")
        return float(v) if v is not None else None
    except Exception:
        return None


async def status_for_child(
    session: AsyncSession, child: Child,
) -> ExcellenceStatus:
    today = today_ist()
    yr_start, yr_end, yr_label = _academic_year_window(today)
    rows = (
        await session.execute(
            select(VeracrossItem)
            .where(VeracrossItem.child_id == child.id)
            .where(VeracrossItem.kind == "grade")
        )
    ).scalars().all()

    grades_in_year: list[tuple[date, float, VeracrossItem]] = []
    for r in rows:
        d = _parse_loose_date(r.due_or_date)
        if d is None or d < yr_start or d > yr_end:
            continue
        pct = _grade_pct(r)
        if pct is None:
            continue
        grades_in_year.append((d, pct, r))

    grades_count = len(grades_in_year)
    above_85_count = sum(1 for _, p, _ in grades_in_year if p >= EXCELLENCE_THRESHOLD)
    avg = (
        sum(p for _, p, _ in grades_in_year) / grades_count
        if grades_count > 0 else None
    )
    above_share = (above_85_count / grades_count) if grades_count > 0 else 0.0
    on_track = avg is not None and avg >= EXCELLENCE_THRESHOLD

    # Surface the 5 most-recent below-85% grades so the parent has a
    # quick "where did this slip" pointer.
    below_85 = sorted(
        [(d, p, r) for d, p, r in grades_in_year if p < EXCELLENCE_THRESHOLD],
        key=lambda x: x[0],
        reverse=True,
    )[:5]
    below_85_recent = [
        {
            "id": r.id,
            "subject": r.subject,
            "title": r.title,
            "graded_date": d.isoformat(),
            "grade_pct": p,
        }
        for d, p, r in below_85
    ]

    return ExcellenceStatus(
        child_id=child.id,
        year_label=yr_label,
        year_start=yr_start.isoformat(),
        year_end=yr_end.isoformat(),
        grades_count=grades_count,
        above_85_count=above_85_count,
        current_year_avg=avg,
        on_track=on_track,
        above_85_share=above_share,
        below_85_recent=below_85_recent,
    )


async def status_for_all(session: AsyncSession) -> list[dict[str, Any]]:
    children = (await session.execute(select(Child))).scalars().all()
    return [
        (await status_for_child(session, c)).to_dict()
        for c in children
    ]
