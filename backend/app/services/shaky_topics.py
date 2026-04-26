"""Shaky topics — surface the 2-3 topics per kid that most warrant a
review conversation this week.

Honest framing per the pedagogy research synthesis:
- We deliberately CAP the list (default 3 per kid). The Hill & Tyson
  meta-analysis warned that pushing parents into "do this together"
  mode lowers achievement; pushing 10+ items would just trigger that.
- We DON'T tell the parent to "drill" — the rec is "talk about this".
- Every item carries a `why` so the parent can explain to the kid.

Ranking signals (additive score, higher = shakier):
    decaying state                    +5  (proficient/mastered + stale)
    last_score < 70 % (familiar floor) +3
    70 ≤ last_score < 80 %             +2
    days since last_assessed > 14      +1 per fortnight overdue
    not seen for ≥ 60 days             +2 (decayed without ever leveling up)
    only 1 attempt total               +0 (don't punish freshness)

Excludes:
    state == "mastered"   (no review needed)
    no graded data yet    (attempted with no score — can't judge)
    last_score ≥ 90 %     (recently strong, leave alone)

Returns ranked top-N per kid.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Child, TopicState
from ..util.time import today_ist


def _shakiness(row: TopicState, today: date) -> tuple[float, list[str]]:
    """Return (score, reasons[]). Higher score = more in need of review."""
    score = 0.0
    reasons: list[str] = []

    if row.state == "decaying":
        score += 5
        reasons.append("decaying — needs refresher")
    elif row.state == "attempted":
        score += 1
        reasons.append("attempted but not yet familiar")

    if row.last_score is not None:
        if row.last_score < 70:
            score += 3
            reasons.append(f"last grade {row.last_score:.0f} % (under 70)")
        elif row.last_score < 80:
            score += 2
            reasons.append(f"last grade {row.last_score:.0f} % (under 80)")

    if row.last_assessed_at:
        try:
            d = date.fromisoformat(row.last_assessed_at)
            age = (today - d).days
            if age > 60:
                score += 2
                reasons.append(f"not assessed in {age} days")
            elif age > 14:
                score += age // 14
                reasons.append(f"last assessed {age} days ago")
        except ValueError:
            pass

    return (score, reasons)


def _exclude(row: TopicState) -> bool:
    if row.state == "mastered":
        return True
    if row.attempt_count == 0:
        return True
    # Already strong recently — don't bother the parent.
    if row.last_score is not None and row.last_score >= 90:
        return True
    # No grade yet (just assignments tagged). Honest: we can't infer
    # weakness from "tagged-not-graded" — it's noise, not signal.
    if row.last_score is None:
        return True
    return False


async def shaky_for_child(
    session: AsyncSession,
    child: Child,
    *,
    limit: int = 3,
) -> list[dict[str, Any]]:
    today = today_ist()
    rows = (
        await session.execute(
            select(TopicState).where(TopicState.child_id == child.id)
        )
    ).scalars().all()

    ranked: list[tuple[float, list[str], TopicState]] = []
    for r in rows:
        if _exclude(r):
            continue
        s, reasons = _shakiness(r, today)
        if s <= 0:
            continue
        ranked.append((s, reasons, r))
    ranked.sort(key=lambda x: -x[0])

    return [
        {
            "child_id": child.id,
            "subject": r.subject,
            "topic": r.topic,
            "state": r.state,
            "last_score": r.last_score,
            "last_assessed_at": r.last_assessed_at,
            "attempt_count": r.attempt_count,
            "shakiness": s,
            "reasons": reasons,
        }
        for s, reasons, r in ranked[:limit]
    ]


async def shaky_for_all(
    session: AsyncSession,
    *,
    limit_per_kid: int = 3,
) -> dict[str, Any]:
    children = (await session.execute(select(Child))).scalars().all()
    by_kid: list[dict[str, Any]] = []
    for c in children:
        items = await shaky_for_child(session, c, limit=limit_per_kid)
        by_kid.append({
            "child_id": c.id,
            "display_name": c.display_name,
            "items": items,
        })
    return {"kids": by_kid, "limit_per_kid": limit_per_kid}
