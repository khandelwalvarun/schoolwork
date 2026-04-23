"""Shared query layer used by both FastAPI routes and MCP tools.

Every function returns plain dicts/lists — JSON-safe, transport-agnostic.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import desc, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import get_settings
from ..models import Child, Event, Notification, ParentNote, Summary, SyncRun, VeracrossItem

IST = ZoneInfo("Asia/Kolkata")


def _now_ist() -> datetime:
    return datetime.now(tz=IST)


def _today_ist() -> date:
    return _now_ist().date()


def _item_to_dict(item: VeracrossItem) -> dict[str, Any]:
    out: dict[str, Any] = {
        "id": item.id,
        "child_id": item.child_id,
        "kind": item.kind,
        "external_id": item.external_id,
        "subject": item.subject,
        "title": item.title,
        "due_or_date": item.due_or_date,
        "status": item.status,
        "first_seen_at": item.first_seen_at.isoformat() if item.first_seen_at else None,
        "last_seen_at": item.last_seen_at.isoformat() if item.last_seen_at else None,
        "seen_at": item.seen_at.isoformat() if item.seen_at else None,
    }
    if item.normalized_json:
        try:
            out["normalized"] = json.loads(item.normalized_json)
        except Exception:
            pass
    return out


async def list_children(session: AsyncSession) -> list[dict[str, Any]]:
    rows = (await session.execute(select(Child).order_by(Child.class_level.desc()))).scalars().all()
    return [
        {
            "id": c.id,
            "display_name": c.display_name,
            "class_level": c.class_level,
            "class_section": c.class_section,
            "school": c.school,
            "veracross_id": c.veracross_id,
        }
        for c in rows
    ]


async def _assignments_query(
    session: AsyncSession,
    child_id: int | None,
    status_in: tuple[str, ...] | None = None,
    status_not_in: tuple[str, ...] | None = None,
    due_before: date | None = None,
    due_after: date | None = None,
    due_on: date | None = None,
    limit: int | None = None,
):
    q = select(VeracrossItem).where(VeracrossItem.kind == "assignment")
    if child_id is not None:
        q = q.where(VeracrossItem.child_id == child_id)
    if status_in:
        q = q.where(VeracrossItem.status.in_(status_in))
    if status_not_in:
        q = q.where(~VeracrossItem.status.in_(status_not_in))
    if due_before is not None:
        q = q.where(VeracrossItem.due_or_date < due_before.isoformat())
    if due_after is not None:
        q = q.where(VeracrossItem.due_or_date > due_after.isoformat())
    if due_on is not None:
        q = q.where(VeracrossItem.due_or_date == due_on.isoformat())
    q = q.order_by(VeracrossItem.due_or_date)
    if limit:
        q = q.limit(limit)
    return [_item_to_dict(r) for r in (await session.execute(q)).scalars().all()]


async def get_overdue(session: AsyncSession, child_id: int | None = None) -> list[dict[str, Any]]:
    return await _assignments_query(
        session,
        child_id=child_id,
        status_not_in=("submitted", "graded", "dismissed"),
        due_before=_today_ist(),
    )


async def get_due_today(session: AsyncSession, child_id: int | None = None) -> list[dict[str, Any]]:
    return await _assignments_query(
        session,
        child_id=child_id,
        status_not_in=("submitted", "graded", "dismissed"),
        due_on=_today_ist(),
    )


async def get_upcoming(
    session: AsyncSession, child_id: int | None = None, days: int = 14
) -> list[dict[str, Any]]:
    today = _today_ist()
    end = today + timedelta(days=days)
    q = (
        select(VeracrossItem)
        .where(VeracrossItem.kind == "assignment")
        .where(VeracrossItem.due_or_date > today.isoformat())
        .where(VeracrossItem.due_or_date <= end.isoformat())
    )
    if child_id is not None:
        q = q.where(VeracrossItem.child_id == child_id)
    q = q.order_by(VeracrossItem.due_or_date)
    return [_item_to_dict(r) for r in (await session.execute(q)).scalars().all()]


async def get_messages(
    session: AsyncSession, since: datetime | None = None, unread_only: bool = False
) -> list[dict[str, Any]]:
    q = select(VeracrossItem).where(
        VeracrossItem.kind.in_(("message", "school_message"))
    )
    if since is not None:
        q = q.where(VeracrossItem.first_seen_at >= since)
    if unread_only:
        q = q.where(VeracrossItem.seen_at.is_(None))
    q = q.order_by(VeracrossItem.first_seen_at.desc())
    return [_item_to_dict(r) for r in (await session.execute(q)).scalars().all()]


async def get_events(
    session: AsyncSession,
    since: datetime | None = None,
    kinds: tuple[str, ...] | None = None,
    child_id: int | None = None,
    limit: int = 200,
) -> list[dict[str, Any]]:
    q = select(Event)
    if since is not None:
        q = q.where(Event.created_at >= since)
    if kinds:
        q = q.where(Event.kind.in_(kinds))
    if child_id is not None:
        q = q.where(Event.child_id == child_id)
    q = q.order_by(Event.created_at.desc()).limit(limit)
    events = (await session.execute(q)).scalars().all()

    if not events:
        return []

    event_ids = [e.id for e in events]
    notifs = (
        await session.execute(
            select(Notification).where(Notification.event_id.in_(event_ids))
        )
    ).scalars().all()
    by_event: dict[int, list[dict[str, Any]]] = {}
    for n in notifs:
        by_event.setdefault(n.event_id, []).append(
            {
                "channel": n.channel,
                "status": n.status,
                "delivered_at": n.delivered_at.isoformat() if n.delivered_at else None,
                "error": n.error,
            }
        )

    return [
        {
            "id": e.id,
            "kind": e.kind,
            "child_id": e.child_id,
            "subject": e.subject,
            "notability": e.notability,
            "dedup_key": e.dedup_key,
            "created_at": e.created_at.isoformat() if e.created_at else None,
            "payload": json.loads(e.payload_json) if e.payload_json else {},
            "notifications": by_event.get(e.id, []),
        }
        for e in events
    ]


async def get_latest_sync(session: AsyncSession) -> dict[str, Any] | None:
    row = (
        await session.execute(select(SyncRun).order_by(desc(SyncRun.started_at)).limit(1))
    ).scalar_one_or_none()
    if row is None:
        return None
    return {
        "id": row.id,
        "started_at": row.started_at.isoformat() if row.started_at else None,
        "ended_at": row.ended_at.isoformat() if row.ended_at else None,
        "trigger": row.trigger,
        "status": row.status,
        "items_new": row.items_new,
        "items_updated": row.items_updated,
        "events_produced": row.events_produced,
        "notifications_fired": row.notifications_fired,
        "error": row.error,
    }


async def get_digest_summary(
    session: AsyncSession, d: date | None = None, kind: str = "digest_4pm"
) -> dict[str, Any] | None:
    d = d or _today_ist()
    row = (
        await session.execute(
            select(Summary).where(Summary.kind == kind).where(Summary.period_start == d.isoformat())
        )
    ).scalar_one_or_none()
    if row is None:
        return None
    return {
        "kind": row.kind,
        "period_start": row.period_start,
        "period_end": row.period_end,
        "content_md": row.content_md,
        "stats": json.loads(row.stats_json) if row.stats_json else {},
        "model_used": row.model_used,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


async def get_today(session: AsyncSession) -> dict[str, Any]:
    """The Today view data shape. Same structure used by the 4pm digest renderers."""
    children = await list_children(session)
    per_kid: list[dict[str, Any]] = []
    totals = {"overdue": 0, "due_today": 0, "upcoming": 0}
    for c in children:
        overdue = await get_overdue(session, c["id"])
        due_today = await get_due_today(session, c["id"])
        upcoming = await get_upcoming(session, c["id"])
        totals["overdue"] += len(overdue)
        totals["due_today"] += len(due_today)
        totals["upcoming"] += len(upcoming)
        per_kid.append(
            {
                "child": c,
                "overdue": overdue,
                "due_today": due_today,
                "upcoming": upcoming,
            }
        )
    messages_since = _now_ist() - timedelta(days=7)
    messages = await get_messages(session, since=messages_since)
    last_sync = await get_latest_sync(session)
    return {
        "generated_at": _now_ist().isoformat(),
        "totals": totals,
        "children": per_kid,
        "messages_last_7d": messages,
        "last_sync": last_sync,
    }


async def add_parent_note(
    session: AsyncSession,
    text: str,
    child_id: int | None = None,
    tags: str | None = None,
) -> dict[str, Any]:
    note = ParentNote(note=text, child_id=child_id, tags=tags)
    session.add(note)
    await session.commit()
    await session.refresh(note)
    return {"id": note.id, "created_at": note.created_at.isoformat() if note.created_at else None}


_SPARK_CHARS = "▁▂▃▄▅▆▇█"


def _sparkline(values: list[float]) -> str:
    if not values:
        return ""
    lo, hi = min(values), max(values)
    if hi - lo < 1e-6:
        return _SPARK_CHARS[4] * len(values)
    rng = hi - lo
    return "".join(_SPARK_CHARS[int((v - lo) / rng * (len(_SPARK_CHARS) - 1))] for v in values)


def _trend_arrow(values: list[float]) -> str:
    if len(values) < 2:
        return "·"
    first_half = values[: len(values) // 2] or [values[0]]
    last_half = values[len(values) // 2 :] or [values[-1]]
    a = sum(first_half) / len(first_half)
    b = sum(last_half) / len(last_half)
    if b > a + 5:
        return "↑"
    if b < a - 5:
        return "↓"
    return "→"


def _parse_grade_date(s: str | None) -> str | None:
    """Parse 'Apr 03' → 'YYYY-MM-DD' assuming current year. Returns None on failure."""
    if not s:
        return None
    import re
    from datetime import datetime as _dt
    m = re.match(r"^(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+(\d{1,2})$", s.strip())
    if not m:
        return s  # already ISO or unknown
    months = {"Jan":1,"Feb":2,"Mar":3,"Apr":4,"May":5,"Jun":6,
              "Jul":7,"Aug":8,"Sep":9,"Oct":10,"Nov":11,"Dec":12}
    try:
        return f"{_dt.now().year}-{months[m.group(1)]:02d}-{int(m.group(2)):02d}"
    except Exception:
        return s


async def get_grades(
    session: AsyncSession,
    child_id: int,
    subject: str | None = None,
    window_days: int = 90,
) -> list[dict[str, Any]]:
    q = select(VeracrossItem).where(
        VeracrossItem.kind == "grade",
        VeracrossItem.child_id == child_id,
    )
    if subject:
        q = q.where(VeracrossItem.subject == subject)
    rows = (await session.execute(q)).scalars().all()
    out: list[dict[str, Any]] = []
    for r in rows:
        d = _item_to_dict(r)
        normalized = d.get("normalized") or {}
        d["grade_pct"] = normalized.get("grade_pct")
        d["points_earned"] = normalized.get("points_earned")
        d["points_possible"] = normalized.get("points_possible")
        d["score_text"] = normalized.get("score_text")
        d["graded_date"] = _parse_grade_date(d.get("due_or_date"))
        out.append(d)
    out.sort(key=lambda x: x.get("graded_date") or "")
    return out


async def get_grade_trends(
    session: AsyncSession,
    child_id: int,
    window_days: int = 30,
) -> list[dict[str, Any]]:
    """One row per subject with a sparkline + recent grades list."""
    from collections import defaultdict
    all_grades = await get_grades(session, child_id=child_id)
    by_subj: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for g in all_grades:
        if g.get("grade_pct") is None:
            continue
        by_subj[g.get("subject") or "Unknown"].append(g)

    trends: list[dict[str, Any]] = []
    for subj, grades in by_subj.items():
        grades_sorted = sorted(grades, key=lambda g: g.get("graded_date") or "")
        values = [float(g["grade_pct"]) for g in grades_sorted if g.get("grade_pct") is not None]
        if not values:
            continue
        trends.append(
            {
                "subject": subj,
                "count": len(values),
                "latest": values[-1],
                "avg": sum(values) / len(values),
                "min": min(values),
                "max": max(values),
                "sparkline": _sparkline(values),
                "arrow": _trend_arrow(values),
                "recent": grades_sorted[-5:],
            }
        )
    trends.sort(key=lambda t: t["subject"])
    return trends


async def search(
    session: AsyncSession,
    query: str,
    child_id: int | None = None,
    kinds: tuple[str, ...] | None = None,
    since: datetime | None = None,
    limit: int = 10,
) -> list[dict[str, Any]]:
    """FTS5 search over the search_index virtual table.

    Returns ranked rows; caller (an LLM) composes the prose answer.
    """
    if not query or not query.strip():
        return []
    # Escape bare FTS operators; simplest: wrap terms in double-quotes so the
    # user query is treated as a phrase-or-words search.
    q = query.replace('"', "").strip()
    fts_q = " ".join(f'"{tok}"' for tok in q.split() if tok)
    if not fts_q:
        return []

    sql = (
        "SELECT kind, child_id, subject, title, snippet(search_index, 4, '[', ']', ' … ', 32) AS snippet, "
        "external_id, created_at, bm25(search_index) AS score "
        "FROM search_index WHERE search_index MATCH :q"
    )
    params: dict[str, Any] = {"q": fts_q}
    if child_id is not None:
        sql += " AND child_id = :cid"
        params["cid"] = str(child_id)
    if kinds:
        placeholders = ",".join(f":k{i}" for i in range(len(kinds)))
        sql += f" AND kind IN ({placeholders})"
        for i, k in enumerate(kinds):
            params[f"k{i}"] = k
    if since is not None:
        sql += " AND created_at >= :since"
        params["since"] = since.isoformat()
    sql += " ORDER BY score LIMIT :lim"
    params["lim"] = limit

    rows = (await session.execute(text(sql), params)).all()
    return [
        {
            "kind": r.kind,
            "child_id": r.child_id,
            "subject": r.subject,
            "title": r.title,
            "snippet": r.snippet,
            "external_id": r.external_id,
            "created_at": r.created_at,
            "score": r.score,
        }
        for r in rows
    ]
