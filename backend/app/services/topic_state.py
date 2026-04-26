"""Per-topic mastery state — Khan Academy heuristics + Cepeda decay.

Walks the kid's syllabus topics; for each topic finds the assignments
and grades currently mapped to it via `services.syllabus.fuzzy_topic_for`,
then classifies the topic into one of:

    attempted    — at least one assignment touches the topic; no
                   grade yet (or all grades very weak)
    familiar     — one grade ≥ 75 %
    proficient   — two consecutive grades ≥ 75 %
    mastered     — three consecutive grades ≥ 85 % (Khan's bar)
    decaying     — was previously proficient/mastered but the latest
                   contributing item is older than DECAY_DAYS
                   (Cepeda 2008: review at ~10–20 % of retention horizon;
                   for school work, ~30 days as a default scrim).

A score < 50 % demotes the state by one level (mastered→proficient,
proficient→familiar, etc.). 50–75 % stays at familiar.

Idempotent: rerun any time. The full table for a child is rebuilt on
each call (cheap — there are only a few hundred topics across both
kids, and matching is in-memory).
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Child, TopicState, VeracrossItem
from ..services import syllabus as syl
from ..services.language import language_code_for as _language_code_for
from ..util.time import today_ist

log = logging.getLogger(__name__)


FAMILIAR_PCT = 70.0
PROFICIENT_PCT = 80.0
MASTERED_PCT = 90.0
WEAK_PCT = 50.0
DECAY_DAYS = 30


def _classify(
    grades: list[tuple[date, float]],
    assignment_dates: list[date],
) -> tuple[str, date | None, float | None, int, int]:
    """Compute (state, last_assessed_at, last_score, attempt_count, proficient_count)
    from a topic's contributing items. Inputs are pre-sorted oldest→newest.

    Thresholds are calibrated to Vasant Valley's grading rubric, not Khan's
    softer Western-school cutoffs:
        familiar    ≥ 70 %
        proficient  2× ≥ 80 %
        mastered    3× ≥ 90 %  (matches the 'Excellence' bar at 85+)
        weak        < 50 %     → demote one level"""
    today = today_ist()
    attempt_count = len(grades) + len(assignment_dates)
    if attempt_count == 0:
        return ("attempted", None, None, 0, 0)

    # Newest contributing date, regardless of source.
    last_assessed = max(
        [g[0] for g in grades] + assignment_dates,
        default=None,
    )

    if not grades:
        # Assignments mapped but no grades yet.
        return ("attempted", last_assessed, None, attempt_count, 0)

    # Walk grades newest-first to compute consecutive proficient/mastered run.
    grades_sorted = sorted(grades, reverse=True)  # newest first
    last_score = grades_sorted[0][1]
    proficient_run = 0
    mastered_run = 0
    for _, pct in grades_sorted:
        if pct >= PROFICIENT_PCT:
            proficient_run += 1
        else:
            break
    for _, pct in grades_sorted:
        if pct >= MASTERED_PCT:
            mastered_run += 1
        else:
            break

    if last_score < WEAK_PCT:
        # Demote. If they had been proficient before, fall to familiar.
        state = "familiar" if any(g[1] >= FAMILIAR_PCT for g in grades) else "attempted"
    elif mastered_run >= 3:
        state = "mastered"
    elif proficient_run >= 2:
        state = "proficient"
    elif last_score >= FAMILIAR_PCT:
        state = "familiar"
    else:  # 50..70
        state = "attempted"

    # Decay: if the topic isn't fresh, downgrade visually.
    if last_assessed and state in ("proficient", "mastered"):
        age = (today - last_assessed).days
        if age > DECAY_DAYS:
            state = "decaying"

    return (state, last_assessed, last_score, attempt_count, proficient_run)


def _grade_pct(item: VeracrossItem) -> float | None:
    """Pull grade % out of normalized_json. None if missing/unparseable."""
    if not item.normalized_json:
        return None
    try:
        import json
        n = json.loads(item.normalized_json)
        v = n.get("grade_pct")
        if v is None:
            return None
        return float(v)
    except Exception:
        return None


def _date_of(item: VeracrossItem) -> date | None:
    """Best date we know for the item — graded date for grades, due date
    for assignments. Loose parser handles both ISO and 'Apr 22'."""
    from .grade_match import _parse_loose_date  # share the same parser
    return _parse_loose_date(item.due_or_date)


async def _items_for_child(session: AsyncSession, child_id: int) -> list[VeracrossItem]:
    rows = (
        await session.execute(
            select(VeracrossItem)
            .where(VeracrossItem.child_id == child_id)
            .where(VeracrossItem.kind.in_(("assignment", "grade")))
        )
    ).scalars().all()
    return list(rows)


async def recompute_for_child(session: AsyncSession, child: Child) -> dict[str, Any]:
    """Rebuild the topic_state rows for one kid. Returns counts per state."""
    items = await _items_for_child(session, child.id)
    # Map every item to a syllabus topic via fuzzy match. Items that don't
    # map to anything are dropped (they show up in the kid's pages anyway,
    # they just don't contribute to topic state).
    by_topic: dict[tuple[str, str], dict[str, list]] = {}
    for it in items:
        topic = syl.fuzzy_topic_for(child.class_level, it.subject, it.title)
        if not topic:
            continue
        # `fuzzy_topic_for` returns "<cycle>: <topic>" (e.g. "LC1: Snake
        # Trouble..."). The syllabus UI iterates per-cycle and renders the
        # bare topic, so strip the prefix for storage so the frontend
        # lookup is a clean (subject, topic) match.
        if ": " in topic:
            topic = topic.split(": ", 1)[1]
        subj = syl.normalize_subject(it.subject) or ""
        key = (subj, topic)
        bucket = by_topic.setdefault(key, {"grades": [], "assignment_dates": []})
        d = _date_of(it)
        if it.kind == "grade":
            pct = _grade_pct(it)
            if pct is not None and d is not None:
                bucket["grades"].append((d, pct))
        elif it.kind == "assignment":
            if d is not None:
                bucket["assignment_dates"].append(d)

    # Wipe + rewrite. Cheap; total rows ≤ ~200/kid.
    await session.execute(delete(TopicState).where(TopicState.child_id == child.id))

    counts: dict[str, int] = {
        "attempted": 0, "familiar": 0, "proficient": 0,
        "mastered": 0, "decaying": 0,
    }
    for (subj, topic), bucket in by_topic.items():
        state, last_assessed, last_score, attempts, prof_run = _classify(
            bucket["grades"], bucket["assignment_dates"],
        )
        counts[state] = counts.get(state, 0) + 1
        session.add(TopicState(
            child_id=child.id,
            class_level=child.class_level,
            subject=subj,
            topic=topic,
            state=state,
            last_assessed_at=last_assessed.isoformat() if last_assessed else None,
            last_score=last_score,
            attempt_count=attempts,
            proficient_count=prof_run,
            language_code=_language_code_for(subj),
            updated_at=datetime.now(tz=timezone.utc),
        ))
    await session.commit()
    return {"child_id": child.id, "topics": len(by_topic), "states": counts}


async def recompute_all(session: AsyncSession) -> dict[str, Any]:
    children = (await session.execute(select(Child))).scalars().all()
    out: list[dict[str, Any]] = []
    for c in children:
        out.append(await recompute_for_child(session, c))
    return {"children": out}


async def list_topic_state(
    session: AsyncSession, child_id: int,
) -> list[dict[str, Any]]:
    rows = (
        await session.execute(
            select(TopicState)
            .where(TopicState.child_id == child_id)
            .order_by(TopicState.subject, TopicState.topic)
        )
    ).scalars().all()
    return [
        {
            "subject": r.subject,
            "topic": r.topic,
            "state": r.state,
            "last_assessed_at": r.last_assessed_at,
            "last_score": r.last_score,
            "attempt_count": r.attempt_count,
            "proficient_count": r.proficient_count,
            "language_code": r.language_code or _language_code_for(r.subject),
        }
        for r in rows
    ]
