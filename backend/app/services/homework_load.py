"""Per-week homework load with CBSE-cap reference.

The cockpit can't directly measure time-on-task — we don't have
"kid started at X, finished at Y" telemetry. So this estimates effort
from the number of assignments due each week, with a per-class default
minutes-per-item. The CBSE caps from Circular 52/2020 are surfaced as
a reference horizon, with explicit framing in the API response that
they're official policy, not what most schools actually assign.

CBSE Circular 52/2020 (homework limits):
  Class I–II    none
  Class III–V   2 hours per week
  Class VI–VIII 1 hour per day  ≈ 5–7 hr/week
  Class IX–XII  not specified (school discretion)

Default minutes-per-item is per class band:
  Class I–II    20 min  (the 'no homework' rule means rare items,
                          when they appear, are short)
  Class III–V   25 min
  Class VI–VIII 35 min
  Class IX+     45 min

`extra_minutes_per_item` on the API call lets a parent override the
estimate from Settings (Phase 12.5 follow-up; not yet wired).

Returns per-kid:
  weeks            list of {week_start, items, est_minutes}
  cap_minutes      per-week CBSE policy cap (or None for IX+)
  cap_basis        human-readable description of the cap
  est_minutes_per_item  the multiplier we used
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Child, VeracrossItem
from .grade_match import _parse_loose_date
from ..util.time import today_ist


def _cap_for_class(level: int) -> tuple[int | None, str]:
    """(weekly cap in minutes, basis)."""
    if level <= 2:
        return (0, "CBSE: no homework Class I–II")
    if level <= 5:
        return (120, "CBSE: ≤ 2 hr/week (Class III–V)")
    if level <= 8:
        return (60 * 6, "CBSE: ≤ 1 hr/day (Class VI–VIII) ≈ 6 hr/week")
    return (None, "Not capped (Class IX+; school discretion)")


def _minutes_per_item(level: int) -> int:
    if level <= 2:
        return 20
    if level <= 5:
        return 25
    if level <= 8:
        return 35
    return 45


def _start_of_iso_week(d: date) -> date:
    """Monday of the ISO week containing d."""
    return d - timedelta(days=d.weekday())


async def homework_load(
    session: AsyncSession,
    child: Child,
    *,
    weeks: int = 8,
    extra_minutes_per_item: int | None = None,
) -> dict[str, Any]:
    today = today_ist()
    span_start = _start_of_iso_week(today - timedelta(weeks=weeks - 1))
    span_end = _start_of_iso_week(today) + timedelta(days=6)

    rows = (
        await session.execute(
            select(VeracrossItem)
            .where(VeracrossItem.child_id == child.id)
            .where(VeracrossItem.kind == "assignment")
        )
    ).scalars().all()

    # Bucket items by Monday-of-due-week.
    per_week: dict[date, int] = {}
    cur = span_start
    while cur <= span_end:
        per_week[cur] = 0
        cur += timedelta(days=7)
    for r in rows:
        d = _parse_loose_date(r.due_or_date)
        if d is None or d < span_start or d > span_end:
            continue
        wk = _start_of_iso_week(d)
        per_week[wk] = per_week.get(wk, 0) + 1

    mpi = extra_minutes_per_item or _minutes_per_item(child.class_level)
    cap_min, cap_basis = _cap_for_class(child.class_level)

    weeks_out = sorted(per_week.items())
    return {
        "child_id": child.id,
        "class_level": child.class_level,
        "weeks": [
            {
                "week_start": ws.isoformat(),
                "items": n,
                "est_minutes": n * mpi,
            }
            for ws, n in weeks_out
        ],
        "cap_minutes": cap_min,
        "cap_basis": cap_basis,
        "est_minutes_per_item": mpi,
        "honest_caveat": (
            "Estimates assume "
            f"{mpi} min per assignment for Class {child.class_level}. "
            "We don't measure actual time-on-task; the CBSE caps are "
            "official policy, not what most schools actually assign — "
            "use the line as a reference, not a verdict."
        ),
    }


async def homework_load_all(
    session: AsyncSession,
    *,
    weeks: int = 8,
) -> list[dict[str, Any]]:
    children = (await session.execute(select(Child))).scalars().all()
    return [await homework_load(session, c, weeks=weeks) for c in children]
