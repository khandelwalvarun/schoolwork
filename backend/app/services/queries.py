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
from ..models import Attachment, Child, Event, Notification, ParentNote, Summary, SyncRun, VeracrossItem
from . import assignment_state as ast
from . import freshness as fresh
from . import syllabus as syl
from ..util.time import IST, now_ist, today_ist


async def _child_class_levels(session: AsyncSession) -> dict[int, int]:
    rows = (await session.execute(select(Child.id, Child.class_level))).all()
    return {cid: lvl for cid, lvl in rows}


async def _attachments_for_items(
    session: AsyncSession, item_ids: list[int]
) -> dict[int, list[dict[str, Any]]]:
    if not item_ids:
        return {}
    rows = (
        await session.execute(
            select(Attachment).where(Attachment.item_id.in_(item_ids))
        )
    ).scalars().all()
    out: dict[int, list[dict[str, Any]]] = {}
    for a in rows:
        out.setdefault(a.item_id, []).append(
            {
                "id": a.id,
                "filename": a.filename,
                "mime_type": a.mime_type,
                "size_bytes": a.size_bytes,
                "kind": a.kind,
                "source_kind": a.source_kind,
                "download_url": f"/api/attachments/{a.id}",
                "sha256": a.sha256,
                "downloaded_at": a.downloaded_at.isoformat() if a.downloaded_at else None,
            }
        )
    return out


async def get_attachment_row(session: AsyncSession, att_id: int) -> Attachment | None:
    return (
        await session.execute(select(Attachment).where(Attachment.id == att_id))
    ).scalar_one_or_none()


async def list_attachments(
    session: AsyncSession,
    child_id: int | None = None,
    source_kind: str | None = None,
    limit: int = 200,
) -> list[dict[str, Any]]:
    q = select(Attachment)
    if child_id is not None:
        q = q.where(Attachment.child_id == child_id)
    if source_kind is not None:
        q = q.where(Attachment.source_kind == source_kind)
    q = q.order_by(Attachment.downloaded_at.desc()).limit(limit)
    rows = (await session.execute(q)).scalars().all()
    # Also join item title for context
    item_ids = [r.item_id for r in rows if r.item_id]
    item_titles: dict[int, tuple[str | None, str | None, str | None]] = {}
    if item_ids:
        item_rows = (
            await session.execute(
                select(VeracrossItem.id, VeracrossItem.title, VeracrossItem.subject, VeracrossItem.kind)
                .where(VeracrossItem.id.in_(item_ids))
            )
        ).all()
        item_titles = {rid: (rtitle, rsubj, rkind) for rid, rtitle, rsubj, rkind in item_rows}
    out: list[dict[str, Any]] = []
    for a in rows:
        t = item_titles.get(a.item_id or 0, (None, None, None))
        out.append(
            {
                "id": a.id,
                "filename": a.filename,
                "mime_type": a.mime_type,
                "size_bytes": a.size_bytes,
                "kind": a.kind,
                "source_kind": a.source_kind,
                "item_id": a.item_id,
                "item_title": t[0],
                "item_subject": syl.normalize_subject(t[1]),
                "item_kind": t[2],
                "child_id": a.child_id,
                "download_url": f"/api/attachments/{a.id}",
                "sha256": a.sha256,
                "downloaded_at": a.downloaded_at.isoformat() if a.downloaded_at else None,
            }
        )
    return out


# Legacy name aliases — canonical helpers now live in util.time.
_now_ist = now_ist
_today_ist = today_ist


def _item_to_dict(
    item: VeracrossItem,
    class_level: int | None = None,
) -> dict[str, Any]:
    parent_marked = item.parent_marked_submitted_at
    subject_clean = syl.normalize_subject(item.subject)
    parent_status = getattr(item, "parent_status", None)
    eff = ast.effective_status(item.status, parent_status)
    out: dict[str, Any] = {
        "id": item.id,
        "child_id": item.child_id,
        "kind": item.kind,
        "external_id": item.external_id,
        "subject": subject_clean,          # prefer cleaned — strips "6B " prefix
        "subject_raw": item.subject,       # keep the raw label if the UI ever needs it
        "title": item.title,
        "title_en": item.title_en,
        "notes_en": item.notes_en,
        "body": getattr(item, "body", None),
        "due_or_date": item.due_or_date,
        "status": item.status,               # raw portal_status
        "portal_status": item.status,
        "parent_status": parent_status,
        "priority": getattr(item, "priority", 0) or 0,
        "snooze_until": getattr(item, "snooze_until", None),
        "status_notes": getattr(item, "status_notes", None),
        "tags": ast.parse_tags(getattr(item, "tags_json", None)),
        "effective_status": eff,
        "parent_marked_submitted_at": parent_marked.isoformat() if parent_marked else None,
        "first_seen_at": item.first_seen_at.isoformat() if item.first_seen_at else None,
        "last_seen_at": item.last_seen_at.isoformat() if item.last_seen_at else None,
        "seen_at": item.seen_at.isoformat() if item.seen_at else None,
        "linked_assignment_id": getattr(item, "linked_assignment_id", None),
        "match_confidence": getattr(item, "match_confidence", None),
        "match_method": getattr(item, "match_method", None),
        "self_prediction": getattr(item, "self_prediction", None),
        "self_prediction_set_at": (
            getattr(item, "self_prediction_set_at", None).isoformat()
            if getattr(item, "self_prediction_set_at", None) else None
        ),
        "self_prediction_outcome": getattr(item, "self_prediction_outcome", None),
        "llm_summary": getattr(item, "llm_summary", None),
        "discuss_with_teacher_at": (
            getattr(item, "discuss_with_teacher_at", None).isoformat()
            if getattr(item, "discuss_with_teacher_at", None) else None
        ),
        "discuss_with_teacher_note": getattr(item, "discuss_with_teacher_note", None),
    }
    if item.normalized_json:
        try:
            out["normalized"] = json.loads(item.normalized_json)
        except Exception:
            pass
    if item.kind == "assignment" and class_level is not None:
        out["syllabus_context"] = syl.fuzzy_topic_for(class_level, item.subject, item.title)
    # Attention-zone is computed last so it can read every field above.
    out["attention_zone"] = fresh.attention_zone(out)
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
    exclude_parent_marked: bool = False,
    class_levels: dict[int, int] | None = None,
):
    q = select(VeracrossItem).where(VeracrossItem.kind == "assignment")
    if child_id is not None:
        q = q.where(VeracrossItem.child_id == child_id)
    if status_in:
        q = q.where(VeracrossItem.status.in_(status_in))
    if status_not_in:
        q = q.where(~VeracrossItem.status.in_(status_not_in))
    if exclude_parent_marked:
        # Exclude items that the parent has marked in any "terminal" state.
        # Legacy parent_marked_submitted_at also kept for back-compat rows.
        q = q.where(VeracrossItem.parent_marked_submitted_at.is_(None))
        q = q.where(
            (VeracrossItem.parent_status.is_(None))
            | (~VeracrossItem.parent_status.in_(
                ("submitted", "done_at_home", "skipped", "blocked")
            ))
        )
    if due_before is not None:
        q = q.where(VeracrossItem.due_or_date < due_before.isoformat())
    if due_after is not None:
        q = q.where(VeracrossItem.due_or_date > due_after.isoformat())
    if due_on is not None:
        q = q.where(VeracrossItem.due_or_date == due_on.isoformat())
    q = q.order_by(VeracrossItem.due_or_date)
    if limit:
        q = q.limit(limit)
    if class_levels is None:
        class_levels = await _child_class_levels(session)
    items = (await session.execute(q)).scalars().all()
    att_map = await _attachments_for_items(session, [i.id for i in items])
    dicts: list[dict[str, Any]] = []
    for r in items:
        d = _item_to_dict(r, class_level=class_levels.get(r.child_id))
        d["attachments"] = att_map.get(r.id, [])
        dicts.append(d)
    return dicts


async def get_overdue(session: AsyncSession, child_id: int | None = None) -> list[dict[str, Any]]:
    rows = await _assignments_query(
        session,
        child_id=child_id,
        status_not_in=("submitted", "graded", "dismissed"),
        due_before=_today_ist(),
        exclude_parent_marked=True,
    )
    return _filter_snooze(rows)


async def get_due_today(session: AsyncSession, child_id: int | None = None) -> list[dict[str, Any]]:
    rows = await _assignments_query(
        session,
        child_id=child_id,
        status_not_in=("submitted", "graded", "dismissed"),
        due_on=_today_ist(),
        exclude_parent_marked=True,
    )
    return _filter_snooze(rows)


def _filter_snooze(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Hide items whose snooze_until is in the future (compared to today in IST)."""
    today_iso = _today_ist().isoformat()
    return [r for r in rows if not (r.get("snooze_until") and r["snooze_until"] > today_iso)]


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
    class_levels = await _child_class_levels(session)
    items = (await session.execute(q)).scalars().all()
    att_map = await _attachments_for_items(session, [i.id for i in items])
    rows = [
        {**_item_to_dict(r, class_level=class_levels.get(r.child_id)),
         "attachments": att_map.get(r.id, [])}
        for r in items
    ]
    return _filter_snooze(rows)


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
    items = (await session.execute(q)).scalars().all()
    att_map = await _attachments_for_items(session, [i.id for i in items])
    return [
        {**_item_to_dict(r), "attachments": att_map.get(r.id, [])}
        for r in items
    ]


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
        why: dict[str, Any] | None = None
        if n.why_json:
            try:
                why = json.loads(n.why_json)
            except Exception:
                why = None
        by_event.setdefault(n.event_id, []).append(
            {
                "channel": n.channel,
                "status": n.status,
                "delivered_at": n.delivered_at.isoformat() if n.delivered_at else None,
                "error": n.error,
                "tier": n.tier,
                "rule_id": n.rule_id,
                "why": why,
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


async def fresh_grade_pellets(
    session: AsyncSession,
    child_id: int,
    *,
    hours: int = fresh.FRESH_WINDOW_HOURS,
    include_anomalies: bool = True,
    limit_fresh: int = 4,
    limit_anomalies: int = 2,
) -> list[dict[str, Any]]:
    """Recently-graded items + still-prominent anomalies for a kid's
    header-pellet strip. Returns at most `limit` rows, newest first.

    `include_anomalies=True` (default) keeps off-trend grades visible
    past the freshness window — the only signal the UI lets cross the
    fresh→steady boundary. They render with tone='red'.

    Each pellet:
        {item_id, subject, pct, score_text, graded_date, hours_ago,
         tone, anomalous}
    """
    from datetime import datetime as _dt
    from .grade_match import _parse_loose_date

    today_d = _today_ist()
    threshold = today_d - timedelta(hours=hours, days=0).resolution * 0  # noqa: F841 (use date math below)
    threshold_d = today_d - timedelta(days=max(1, hours // 24 + 1))

    # Pull every grade for the kid; filter loose-date in Python because
    # due_or_date can be "2026-04-30" OR "May 22" depending on source.
    q = (
        select(VeracrossItem)
        .where(VeracrossItem.child_id == child_id)
        .where(VeracrossItem.kind == "grade")
        .order_by(VeracrossItem.due_or_date.desc())
    )
    all_rows = (await session.execute(q)).scalars().all()
    # Pre-filter by parsed date to keep the loop tight. Exclude future-dated
    # rows (some grades are stamped with the cycle's end date, not the
    # grading date — those would otherwise show as "fresh" forever).
    rows = [
        r for r in all_rows
        if (d := _parse_loose_date(r.due_or_date))
        and d >= threshold_d and d <= today_d
    ]

    # Anomaly set — small list, fetched via the existing detector.
    anomaly_ids: set[int] = set()
    if include_anomalies:
        try:
            from .anomaly import detect_anomalies_for_child
            anomalies = await detect_anomalies_for_child(session, child_id)
            anomaly_ids = {int(a.get("grade_id", 0)) for a in anomalies if a.get("grade_id")}
        except Exception:
            pass

    # Build pellet payloads — split into "fresh-real" and "anomaly-extra"
    # so each gets its own quota; fresh wins ties on newness.
    out: list[dict[str, Any]] = []
    now_d = today_d
    seen: set[int] = set()
    sources: list[tuple[list[VeracrossItem], int, bool]] = [
        (rows, limit_fresh, False),
    ]
    if include_anomalies and anomaly_ids:
        anomaly_rows = [
            r for r in all_rows
            if r.id in anomaly_ids and r.id not in {x.id for x in rows}
        ]
        sources.append((anomaly_rows, limit_anomalies, True))

    for source_rows, cap, anomaly_only in sources:
        added = 0
        for r in source_rows:
            if added >= cap:
                break
            if r.id in seen:
                continue
            try:
                n = json.loads(r.normalized_json or "{}")
            except Exception:
                n = {}
            pct = n.get("grade_pct")
            if pct is None:
                continue
            try:
                pct_val = float(pct)
            except (TypeError, ValueError):
                continue
            graded_at_d = _parse_loose_date(r.due_or_date)
            hours_ago = (
                int((now_d - graded_at_d).days * 24)
                if graded_at_d else None
            )
            anomalous = r.id in anomaly_ids
            out.append({
                "item_id": r.id,
                "subject": syl.normalize_subject(r.subject) or r.subject,
                "title": r.title,
                "pct": pct_val,
                "score_text": n.get("score_text"),
                "graded_date": graded_at_d.isoformat() if graded_at_d else None,
                "hours_ago": hours_ago,
                "tone": fresh.grade_pellet_tone(pct_val, anomalous=anomalous),
                "anomalous": anomalous,
            })
            seen.add(r.id)
            added += 1
    out.sort(key=lambda p: (p["graded_date"] or "", p["item_id"]), reverse=True)
    return out


async def get_today(session: AsyncSession) -> dict[str, Any]:
    """The Today view data shape. Same structure used by the 4pm digest renderers."""
    children = await list_children(session)
    today_d = _today_ist()
    per_kid: list[dict[str, Any]] = []
    totals = {"overdue": 0, "due_today": 0, "upcoming": 0}
    for c in children:
        overdue = await get_overdue(session, c["id"])
        due_today = await get_due_today(session, c["id"])
        upcoming = await get_upcoming(session, c["id"])
        grade_trends = await get_grade_trends(session, c["id"])
        backlog = await get_overdue_trend(session, c["id"], days=14)
        totals["overdue"] += len(overdue)
        totals["due_today"] += len(due_today)
        totals["upcoming"] += len(upcoming)
        cycle = (
            await syl.cycle_for_date_merged(session, c["class_level"], today_d)
            if c.get("class_level") else None
        )
        backlog_counts = [b["count"] for b in backlog]
        pellets = await fresh_grade_pellets(session, c["id"])
        per_kid.append(
            {
                "child": c,
                "overdue": overdue,
                "due_today": due_today,
                "upcoming": upcoming,
                "grade_trends": grade_trends,
                "fresh_pellets": pellets,
                "syllabus_cycle": (
                    {
                        "name": cycle.name,
                        "start": cycle.start.isoformat(),
                        "end": cycle.end.isoformat(),
                    }
                    if cycle else None
                ),
                "overdue_trend": backlog,
                "overdue_sparkline": _overdue_sparkline(backlog_counts),
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


async def get_child_detail(session: AsyncSession, child_id: int) -> dict[str, Any] | None:
    child_row = (
        await session.execute(select(Child).where(Child.id == child_id))
    ).scalar_one_or_none()
    if child_row is None:
        return None
    child = {
        "id": child_row.id,
        "display_name": child_row.display_name,
        "class_level": child_row.class_level,
        "class_section": child_row.class_section,
        "school": child_row.school,
        "veracross_id": child_row.veracross_id,
    }
    overdue = await get_overdue(session, child_id)
    due_today = await get_due_today(session, child_id)
    upcoming = await get_upcoming(session, child_id)
    grade_trends = await get_grade_trends(session, child_id)
    backlog = await get_overdue_trend(session, child_id, days=14)
    cycle = await syl.cycle_for_date_merged(session, child_row.class_level, _today_ist())
    comment_count = (
        await session.execute(
            select(func.count(VeracrossItem.id))
            .where(VeracrossItem.kind == "comment")
            .where(VeracrossItem.child_id == child_id)
        )
    ).scalar_one()
    pellets = await fresh_grade_pellets(session, child_id)
    return {
        "child": child,
        "overdue": overdue,
        "due_today": due_today,
        "upcoming": upcoming,
        "grade_trends": grade_trends,
        "overdue_trend": backlog,
        "overdue_sparkline": _overdue_sparkline([b["count"] for b in backlog]),
        "fresh_pellets": pellets,
        "syllabus_cycle": (
            {"name": cycle.name, "start": cycle.start.isoformat(), "end": cycle.end.isoformat()}
            if cycle else None
        ),
        "counts": {
            "overdue": len(overdue),
            "due_today": len(due_today),
            "upcoming": len(upcoming),
            "comments": comment_count,
        },
    }


async def mark_assignment_submitted(
    session: AsyncSession, item_id: int, submitted: bool = True
) -> dict[str, Any]:
    """Back-compat shortcut — routes through the full state service so that
    changes are audit-logged. `submitted=False` clears to unset.
    """
    r = await ast.update_assignment_state(
        session,
        item_id=item_id,
        patch={"parent_status": "submitted" if submitted else None},
        actor="mark-submitted-shortcut",
    )
    if r is None:
        return {"status": "not_found", "id": item_id}
    item = (
        await session.execute(select(VeracrossItem).where(VeracrossItem.id == item_id))
    ).scalar_one_or_none()
    if item is None:
        return {"status": "not_found", "id": item_id}
    class_levels = await _child_class_levels(session)
    return {"status": "ok", "item": _item_to_dict(item, class_level=class_levels.get(item.child_id))}


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
    att_map = await _attachments_for_items(session, [r.id for r in rows])
    out: list[dict[str, Any]] = []
    for r in rows:
        d = _item_to_dict(r)
        normalized = d.get("normalized") or {}
        d["grade_pct"] = normalized.get("grade_pct")
        d["points_earned"] = normalized.get("points_earned")
        d["points_possible"] = normalized.get("points_possible")
        d["score_text"] = normalized.get("score_text")
        d["graded_date"] = _parse_grade_date(d.get("due_or_date"))
        d["attachments"] = att_map.get(r.id, [])
        out.append(d)
    out.sort(key=lambda x: x.get("graded_date") or "")
    return out


async def get_worth_a_chat(
    session: AsyncSession,
    child_id: int | None = None,
    kind: str | None = None,
    limit: int = 200,
) -> list[dict[str, Any]]:
    """Items the parent flagged as 'worth a chat' at the next PTM.

    Spans every kind (assignments, grades, comments, school messages) —
    the parent might want to discuss a low grade, a confusing comment,
    or a homework that didn't make sense. Sorted by flag time, newest
    first so the most recent concerns surface at the top of the tray.
    """
    q = (
        select(VeracrossItem)
        .where(VeracrossItem.discuss_with_teacher_at.is_not(None))
    )
    if child_id is not None:
        q = q.where(VeracrossItem.child_id == child_id)
    if kind:
        q = q.where(VeracrossItem.kind == kind)
    q = q.order_by(VeracrossItem.discuss_with_teacher_at.desc()).limit(limit)
    class_levels = await _child_class_levels(session)
    items = (await session.execute(q)).scalars().all()
    att_map = await _attachments_for_items(session, [i.id for i in items])
    return [
        {**_item_to_dict(r, class_level=class_levels.get(r.child_id)),
         "attachments": att_map.get(r.id, [])}
        for r in items
    ]


async def get_all_assignments(
    session: AsyncSession,
    child_id: int | None = None,
    subject: str | None = None,
    status: str | None = None,
    limit: int = 500,
) -> list[dict[str, Any]]:
    q = select(VeracrossItem).where(VeracrossItem.kind == "assignment")
    if child_id is not None:
        q = q.where(VeracrossItem.child_id == child_id)
    if subject:
        # Match exact or "<class_section> <subject>" (e.g. "Mathematics" matches
        # both "Mathematics" and "6B Mathematics")
        from sqlalchemy import or_
        q = q.where(
            or_(
                VeracrossItem.subject == subject,
                VeracrossItem.subject.like(f"% {subject}"),
            )
        )
    if status:
        if status == "parent_submitted":
            q = q.where(VeracrossItem.parent_marked_submitted_at.is_not(None))
        else:
            q = q.where(VeracrossItem.status == status)
    q = q.order_by(VeracrossItem.due_or_date.desc()).limit(limit)
    class_levels = await _child_class_levels(session)
    return [
        _item_to_dict(r, class_level=class_levels.get(r.child_id))
        for r in (await session.execute(q)).scalars().all()
    ]


async def get_comments(
    session: AsyncSession, child_id: int | None = None, limit: int = 200
) -> list[dict[str, Any]]:
    q = select(VeracrossItem).where(VeracrossItem.kind == "comment")
    if child_id is not None:
        q = q.where(VeracrossItem.child_id == child_id)
    q = q.order_by(VeracrossItem.first_seen_at.desc()).limit(limit)
    class_levels = await _child_class_levels(session)
    items = (await session.execute(q)).scalars().all()
    att_map = await _attachments_for_items(session, [i.id for i in items])
    return [
        {**_item_to_dict(r, class_level=class_levels.get(r.child_id)),
         "attachments": att_map.get(r.id, [])}
        for r in items
    ]


async def get_notes(
    session: AsyncSession, child_id: int | None = None, limit: int = 200
) -> list[dict[str, Any]]:
    q = select(ParentNote)
    if child_id is not None:
        q = q.where(ParentNote.child_id == child_id)
    q = q.order_by(ParentNote.created_at.desc()).limit(limit)
    rows = (await session.execute(q)).scalars().all()
    return [
        {
            "id": n.id,
            "child_id": n.child_id,
            "note": n.note,
            "tags": n.tags,
            "note_date": n.note_date.isoformat() if n.note_date else None,
            "created_at": n.created_at.isoformat() if n.created_at else None,
        }
        for n in rows
    ]


async def get_summaries(
    session: AsyncSession, kind: str | None = None, limit: int = 60
) -> list[dict[str, Any]]:
    q = select(Summary)
    if kind:
        q = q.where(Summary.kind == kind)
    q = q.order_by(desc(Summary.period_start), desc(Summary.id)).limit(limit)
    rows = (await session.execute(q)).scalars().all()
    return [
        {
            "id": r.id,
            "kind": r.kind,
            "child_id": r.child_id,
            "period_start": r.period_start,
            "period_end": r.period_end,
            "content_md": r.content_md,
            "stats": json.loads(r.stats_json) if r.stats_json else {},
            "model_used": r.model_used,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows
    ]


async def get_overdue_trend(
    session: AsyncSession,
    child_id: int | None = None,
    days: int = 14,
) -> list[dict[str, Any]]:
    """14-day overdue backlog. For each day D in [today-days+1, today] we count
    assignments whose `due_or_date < D` and which appear not-closed for that day:
      - current status is open, OR
      - current status is closed but last_seen_at > D (i.e. closed after D)
      - parent_marked_submitted_at is NULL or > D
    Approximate (we don't store status history), but the shape of the trend is the
    useful signal. Returns [{date, count}] oldest → newest."""
    today = _today_ist()
    q = select(VeracrossItem).where(VeracrossItem.kind == "assignment")
    if child_id is not None:
        q = q.where(VeracrossItem.child_id == child_id)
    rows = (await session.execute(q)).scalars().all()
    closed = {"submitted", "graded", "dismissed"}
    out: list[dict[str, Any]] = []
    for offset in range(days - 1, -1, -1):
        d = today - timedelta(days=offset)
        d_iso = d.isoformat()
        count = 0
        for r in rows:
            if not r.due_or_date or r.due_or_date >= d_iso:
                continue
            # Parent override that predates this day → treat as closed
            pm = r.parent_marked_submitted_at
            if pm is not None and pm.date() <= d:
                continue
            # If currently closed but last_seen before D, assume closed before D too.
            if r.status in closed:
                last = r.last_seen_at.date() if r.last_seen_at else d
                if last <= d:
                    continue
            count += 1
        out.append({"date": d_iso, "count": count})
    return out


async def get_submission_heatmap(
    session: AsyncSession,
    child_id: int | None = None,
    weeks: int = 14,
    pending_grace_days: int = 7,
) -> list[dict[str, Any]]:
    """Daily submission state over the last N weeks. The cockpit can't
    *directly* see whether a kid submitted (the school doesn't mark
    'submitted' reliably and the parent might forget). So this function
    infers a per-day state from what *is* observable:

        graded         portal-side status confirms school graded it
                       (status in {submitted, graded, dismissed})
        parent_marked  parent flagged it done_at_home / submitted
        pending        past due, still 'assigned', age ≤ pending_grace_days
                       (probably handed in, awaiting teacher action)
        likely_missing past due, still 'assigned', older than the grace window
                       (school hasn't graded AND parent hasn't confirmed —
                        looks bad, worth a parent nudge)
        future         due date in the future or no due date

    For each day D in the window, we compute counts of each state across
    assignments whose due_or_date == D. The UI tints heatmap cells by
    these counts (green for graded+parent_marked, amber for pending, red
    for likely_missing, muted gray when nothing was due).

    Per-row inference is computed at "today's" snapshot — i.e. how does
    each item *currently* stand. We don't reconstruct a per-day timeline
    because we don't store enough history; this is honest about what we
    know vs assume.

    Returns [{date, due, graded, parent_marked, pending, likely_missing,
              ratio_closed}] oldest → newest. `closed` is kept for
    backward-compat (graded + parent_marked, the optimistic view)."""
    today = _today_ist()
    days = weeks * 7
    q = select(VeracrossItem).where(VeracrossItem.kind == "assignment")
    if child_id is not None:
        q = q.where(VeracrossItem.child_id == child_id)
    rows = (await session.execute(q)).scalars().all()

    closed_portal = {"submitted", "graded", "dismissed"}
    closed_parent = {"submitted", "graded", "done_at_home"}

    out: list[dict[str, Any]] = []
    for offset in range(days - 1, -1, -1):
        d = today - timedelta(days=offset)
        d_iso = d.isoformat()
        graded = 0
        parent_marked = 0
        pending = 0
        likely_missing = 0
        due_total = 0
        for r in rows:
            if r.due_or_date != d_iso:
                continue
            due_total += 1
            # Order: school > parent > inferred. Each item lands in one bucket.
            if r.status in closed_portal:
                graded += 1
                continue
            if r.parent_status in closed_parent or (
                r.parent_marked_submitted_at is not None
                and r.parent_marked_submitted_at.date() <= d
            ):
                parent_marked += 1
                continue
            # Past due + still 'assigned': age decides.
            if d < today:
                age = (today - d).days
                if age <= pending_grace_days:
                    pending += 1
                else:
                    likely_missing += 1
            # else: future-dated, no bucket beyond `due_total`.
        closed = graded + parent_marked
        ratio = (closed / due_total) if due_total > 0 else 0.0
        out.append({
            "date": d_iso,
            "due": due_total,
            "graded": graded,
            "parent_marked": parent_marked,
            "pending": pending,
            "likely_missing": likely_missing,
            "closed": closed,           # back-compat: graded + parent_marked
            "ratio": ratio,             # back-compat: closed/due
        })
    return out


def _overdue_sparkline(values: list[int]) -> str:
    if not values:
        return ""
    floats = [float(v) for v in values]
    return _sparkline(floats)


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
