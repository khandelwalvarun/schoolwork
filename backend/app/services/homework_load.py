"""Per-week homework-load estimator (no policy cap).

The cockpit can't directly measure time-on-task — we don't have
"kid started at X, finished at Y" telemetry. So this estimates effort
from when assignments LAND (date_assigned), not when they're due. A
worksheet assigned Monday and due Friday creates work across the
Monday-Friday range; bucketing by due-day would falsely make Friday
look like a 5-hr crush.

If date_assigned isn't available (rows that only saw the planner-only
path) we fall back to due_or_date with a per-bucket source split so
the UI can footnote it. After enough syncs run the back-fill detail-
pass, every row should have an assigned date.

Default minutes-per-item is per class band — a rough estimate for the
chart only. The CBSE Circular 52/2020 caps that earlier versions
plotted as a reference horizon were removed: in practice they bear
no resemblance to what the school assigns and the parent flagged the
line as misleading.

  Class I–II    20 min  (rare items, when they appear, are short)
  Class III–V   25 min
  Class VI–VIII 35 min
  Class IX+     45 min

`extra_minutes_per_item` on the API call lets a parent override the
estimate from Settings.

Returns per-kid:
  weeks                 list of {week_start, items, est_minutes, by_source}
  est_minutes_per_item  the multiplier we used
  bucketing             "assigned_date_with_due_fallback"
  fallback_share        share (0..1) of items that had no assigned date
  bucketing_note        human-readable footnote for the UI
  honest_caveat         standard min-resolution disclaimer
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Child, VeracrossItem
from .grade_match import _parse_loose_date
from ..util.time import today_ist


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


def _date_assigned_for(item: VeracrossItem) -> tuple[date | None, str]:
    """Return (date, source) where source ∈ {'assigned','due'}.

    Prefers normalized_json["date_assigned"] when present; falls back
    to due_or_date with source='due' so the caller can flag bucket
    accuracy in the response. Both date strings are run through the
    same loose parser used elsewhere ("Apr 22" / "22 Apr" / ISO)."""
    import json as _json
    try:
        norm = _json.loads(item.normalized_json or "{}")
    except Exception:
        norm = {}
    da = norm.get("date_assigned") if isinstance(norm, dict) else None
    parsed = _parse_loose_date(da) if da else None
    if parsed is not None:
        return parsed, "assigned"
    return _parse_loose_date(item.due_or_date), "due"


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

    per_week_count: dict[date, int] = {}
    per_week_source: dict[date, dict[str, int]] = {}
    cur = span_start
    while cur <= span_end:
        per_week_count[cur] = 0
        per_week_source[cur] = {"assigned": 0, "due": 0}
        cur += timedelta(days=7)

    fallbacks_to_due = 0
    for r in rows:
        d, source = _date_assigned_for(r)
        if d is None or d < span_start or d > span_end:
            continue
        wk = _start_of_iso_week(d)
        per_week_count[wk] = per_week_count.get(wk, 0) + 1
        bucket = per_week_source.setdefault(wk, {"assigned": 0, "due": 0})
        bucket[source] = bucket.get(source, 0) + 1
        if source == "due":
            fallbacks_to_due += 1

    mpi = extra_minutes_per_item or _minutes_per_item(child.class_level)

    weeks_out = sorted(per_week_count.items())
    total_items = sum(n for _, n in weeks_out)
    fallback_share = (fallbacks_to_due / total_items) if total_items else 0.0

    bucketing_note = (
        "Bucketed by date assigned (when the school gave the work). "
        + (
            f"{fallbacks_to_due} of {total_items} items fell back to due-date "
            "because no assigned-date was captured for them yet — this resolves "
            "after the next heavy sync re-fetches their detail page."
            if fallbacks_to_due
            else "All items had assigned-date metadata."
        )
    )

    return {
        "child_id": child.id,
        "class_level": child.class_level,
        "weeks": [
            {
                "week_start": ws.isoformat(),
                "items": per_week_count[ws],
                "est_minutes": per_week_count[ws] * mpi,
                "by_source": per_week_source[ws],
            }
            for ws, _ in weeks_out
        ],
        "est_minutes_per_item": mpi,
        "bucketing": "assigned_date_with_due_fallback",
        "fallback_share": round(fallback_share, 3),
        "bucketing_note": bucketing_note,
        "honest_caveat": (
            "Estimates assume "
            f"{mpi} min per assignment for Class {child.class_level}, "
            "bucketed by the date the assignment was GIVEN (not when "
            "it's due). We don't measure actual time-on-task; the chart "
            "is for trend-watching, not for grading the school."
        ),
    }


async def homework_load_all(
    session: AsyncSession,
    *,
    weeks: int = 8,
) -> list[dict[str, Any]]:
    children = (await session.execute(select(Child))).scalars().all()
    return [await homework_load(session, c, weeks=weeks) for c in children]
