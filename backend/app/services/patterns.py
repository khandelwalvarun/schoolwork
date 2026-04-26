"""Behavioural-pattern detectors — three quiet monthly flags per kid.

Honest framing: these are *signals* derived from incomplete data, never
verdicts. The school's data has gaps (we don't see real submission
timestamps; "late" is rarely tagged), so each detector states its
threshold and the count that crossed it. The UI shows the flag only
when triggered, with a tooltip listing supporting items.

By design these never push notifications — they sit on the per-kid
Detail page as a passive card. The pedagogy research warned that
behavioural flags can become a moralising lens; staying passive limits
the harm.

Three patterns:

  lateness            ≥ 3 assignments in the month flagged as
                      `likely_missing` (past due + still 'assigned'
                      for >7 d) or `parent_status == 'missing'/'late'`.

  repeated_attempt    same (subject, topic) shows up ≥ 3 times in
                      grades in the month. The topic comes from
                      `fuzzy_topic_for`; grade rows without a topic
                      tag don't count.

  weekend_cramming    ≥ 60 % of `parent_marked_submitted_at` events
                      in the month land on Sat/Sun, with a minimum
                      sample of 5 marks (below that it's noise).

A `detail` JSON blob carries supporting evidence per flag — counts +
a couple of example titles — so the UI's "why?" tooltip doesn't have
to re-derive the math.
"""
from __future__ import annotations

from collections import Counter
from datetime import date, timedelta
from typing import Any

from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Child, PatternState, VeracrossItem
from ..util.time import today_ist
from .grade_match import _parse_loose_date
from .syllabus import fuzzy_topic_for


LATE_MIN_COUNT = 3
REPEAT_MIN_COUNT = 3
WEEKEND_MIN_SAMPLE = 5
WEEKEND_FRAC = 0.60


def _month_str(d: date) -> str:
    return f"{d.year:04d}-{d.month:02d}"


def _months_back(n: int, ref: date | None = None) -> list[str]:
    """Last n calendar months as 'YYYY-MM', oldest → newest. Includes
    the current month."""
    ref = ref or today_ist()
    out: list[str] = []
    y, m = ref.year, ref.month
    for _ in range(n):
        out.append(f"{y:04d}-{m:02d}")
        m -= 1
        if m == 0:
            m = 12
            y -= 1
    out.reverse()
    return out


def _strip_topic_prefix(t: str | None) -> str | None:
    """`fuzzy_topic_for` may return 'LC1: Friend's Prayer' — drop the
    cycle prefix so equivalent items group together."""
    if t is None:
        return None
    if ":" in t:
        head, tail = t.split(":", 1)
        if head.strip().upper().startswith("LC") or head.strip().lower() in {
            "ch", "chapter", "unit",
        }:
            return tail.strip()
    return t.strip()


CLOSED_PORTAL = {"submitted", "graded", "dismissed"}
CLOSED_PARENT = {"submitted", "graded", "done_at_home"}
GRACE_DAYS = 7


def _is_likely_missing(it: VeracrossItem, due: date, today: date) -> bool:
    """Mirror queries.get_submission_heatmap's honest closure rules.
    True iff the item is past-due past the grace window, *not* closed
    by the school, *not* closed by the parent, and not parent-marked
    submitted on/before the due date."""
    if today <= due:
        return False
    if (today - due).days <= GRACE_DAYS:
        return False
    if it.status in CLOSED_PORTAL:
        return False
    if it.parent_status in CLOSED_PARENT:
        return False
    if (
        it.parent_marked_submitted_at is not None
        and it.parent_marked_submitted_at.date() <= due
    ):
        return False
    return True


def _detect_lateness(
    items: list[VeracrossItem], month: str, today: date,
) -> tuple[bool, dict[str, Any]]:
    """Count assignments in `month` that look likely-missing under the
    same rules as the submission heatmap. We avoid drift by reusing the
    closure logic — if the heatmap says 'red', so do we."""
    late_titles: list[str] = []
    for it in items:
        if it.kind != "assignment":
            continue
        d = _parse_loose_date(it.due_or_date)
        if d is None:
            continue
        if _month_str(d) != month:
            continue
        if _is_likely_missing(it, d, today):
            late_titles.append(it.title or it.title_en or f"item {it.id}")
    return (
        len(late_titles) >= LATE_MIN_COUNT,
        {
            "count": len(late_titles),
            "threshold": LATE_MIN_COUNT,
            "examples": late_titles[:5],
        },
    )


def _detect_repeated_attempt(
    items: list[VeracrossItem], month: str, child_class_level: int,
) -> tuple[bool, dict[str, Any]]:
    """Count grades in `month` per (subject, topic). If any topic
    shows up ≥ REPEAT_MIN_COUNT times, the kid is being reteached."""
    by_topic: Counter[tuple[str, str]] = Counter()
    examples_by_topic: dict[tuple[str, str], list[str]] = {}
    for it in items:
        if it.kind != "grade":
            continue
        d = _parse_loose_date(it.due_or_date)
        if d is None or _month_str(d) != month:
            continue
        topic = _strip_topic_prefix(
            fuzzy_topic_for(child_class_level, it.subject, it.title)
        )
        if not topic or not it.subject:
            continue
        key = (it.subject, topic)
        by_topic[key] += 1
        examples_by_topic.setdefault(key, []).append(
            it.title or it.title_en or f"item {it.id}"
        )

    hits = [(k, n) for k, n in by_topic.items() if n >= REPEAT_MIN_COUNT]
    triggered = len(hits) > 0
    return (
        triggered,
        {
            "topics": [
                {
                    "subject": s,
                    "topic": t,
                    "count": n,
                    "examples": examples_by_topic[(s, t)][:5],
                }
                for (s, t), n in hits
            ],
            "threshold": REPEAT_MIN_COUNT,
        },
    )


def _detect_weekend_cramming(
    items: list[VeracrossItem], month: str,
) -> tuple[bool, dict[str, Any]]:
    """Look at parent_marked_submitted_at events landing in `month`.
    If ≥ 60 % land on Sat/Sun (with min 5 events) → cramming."""
    weekend = 0
    weekday = 0
    sample_titles: list[str] = []
    for it in items:
        ts = it.parent_marked_submitted_at
        if ts is None:
            continue
        d = ts.date()
        if _month_str(d) != month:
            continue
        if d.weekday() >= 5:  # Sat=5, Sun=6
            weekend += 1
            if len(sample_titles) < 5:
                sample_titles.append(it.title or it.title_en or f"item {it.id}")
        else:
            weekday += 1
    total = weekend + weekday
    if total < WEEKEND_MIN_SAMPLE:
        return (
            False,
            {
                "weekend": weekend,
                "weekday": weekday,
                "total": total,
                "min_sample": WEEKEND_MIN_SAMPLE,
                "fraction_threshold": WEEKEND_FRAC,
                "note": "below minimum sample — not enough activity to call it",
            },
        )
    frac = weekend / total
    return (
        frac >= WEEKEND_FRAC,
        {
            "weekend": weekend,
            "weekday": weekday,
            "total": total,
            "fraction": round(frac, 2),
            "fraction_threshold": WEEKEND_FRAC,
            "examples": sample_titles,
        },
    )


async def compute_for_child(
    session: AsyncSession,
    child: Child,
    *,
    months: int = 6,
) -> list[dict[str, Any]]:
    """Compute pattern_state for the last `months` calendar months for
    one kid. Idempotent — replaces the row for each month."""
    items = (
        await session.execute(
            select(VeracrossItem).where(VeracrossItem.child_id == child.id)
        )
    ).scalars().all()

    today = today_ist()
    rows_out: list[dict[str, Any]] = []
    for m in _months_back(months, ref=today):
        late_flag, late_detail = _detect_lateness(items, m, today)
        repeat_flag, repeat_detail = _detect_repeated_attempt(
            items, m, child.class_level,
        )
        weekend_flag, weekend_detail = _detect_weekend_cramming(items, m)

        detail = {
            "lateness": late_detail,
            "repeated_attempt": repeat_detail,
            "weekend_cramming": weekend_detail,
        }

        # Upsert.
        await session.execute(
            delete(PatternState).where(
                PatternState.child_id == child.id,
                PatternState.month == m,
            )
        )
        row = PatternState(
            child_id=child.id,
            month=m,
            lateness=late_flag,
            repeated_attempt=repeat_flag,
            weekend_cramming=weekend_flag,
            detail=detail,
        )
        session.add(row)
        rows_out.append({
            "child_id": child.id,
            "month": m,
            "lateness": late_flag,
            "repeated_attempt": repeat_flag,
            "weekend_cramming": weekend_flag,
            "detail": detail,
        })
    await session.commit()
    return rows_out


async def compute_all(
    session: AsyncSession,
    *,
    months: int = 6,
) -> dict[str, Any]:
    children = (await session.execute(select(Child))).scalars().all()
    total = 0
    for c in children:
        rows = await compute_for_child(session, c, months=months)
        total += len(rows)
    return {"children": len(children), "rows": total, "months": months}


async def list_patterns(
    session: AsyncSession,
    child_id: int,
) -> list[dict[str, Any]]:
    rows = (
        await session.execute(
            select(PatternState)
            .where(PatternState.child_id == child_id)
            .order_by(PatternState.month.desc())
        )
    ).scalars().all()
    return [
        {
            "child_id": r.child_id,
            "month": r.month,
            "lateness": r.lateness,
            "repeated_attempt": r.repeated_attempt,
            "weekend_cramming": r.weekend_cramming,
            "detail": r.detail,
            "updated_at": r.updated_at.isoformat() if r.updated_at else None,
        }
        for r in rows
    ]


async def list_patterns_all(session: AsyncSession) -> dict[str, Any]:
    children = (await session.execute(select(Child))).scalars().all()
    out: list[dict[str, Any]] = []
    for c in children:
        rows = await list_patterns(session, c.id)
        out.append({
            "child_id": c.id,
            "display_name": c.display_name,
            "months": rows,
        })
    return {"kids": out}
