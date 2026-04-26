"""Kid-relevant events: auditions, competitions, camps, exams, etc.

Two ways events land in the table:

  1. Manual entry — parent fills out a form on /events. `source='manual'`.
  2. LLM extraction — `extract_from_school_messages` walks recent
     school_message rows, asks Claude to identify date-bound events,
     and inserts each one with `source='school_message'` and
     `source_ref='school_message:<id>'`. Idempotent on (source_ref,
     normalized_title) so re-runs don't duplicate.

The cockpit displays them on a /events page and the Today header
("upcoming this week"). Past events stay as a passive history.
"""
from __future__ import annotations

import json
import logging
from datetime import date, datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from ..llm.client import LLMClient
from ..models import Child, KidEvent, VeracrossItem
from ..util.time import today_ist
from .grade_match import _parse_loose_date


log = logging.getLogger(__name__)


VALID_TYPES = {
    "audition", "competition", "camp", "exam", "holiday",
    "parent_meeting", "trip", "test", "performance", "deadline", "other",
}


def _row_to_dict(r: KidEvent) -> dict[str, Any]:
    return {
        "id": r.id,
        "child_id": r.child_id,
        "title": r.title,
        "description": r.description,
        "event_type": r.event_type,
        "importance": r.importance,
        "start_date": r.start_date,
        "end_date": r.end_date,
        "start_time": r.start_time,
        "location": r.location,
        "source": r.source,
        "source_ref": r.source_ref,
        "notes": r.notes,
        "created_at": r.created_at.isoformat() if r.created_at else None,
        "updated_at": r.updated_at.isoformat() if r.updated_at else None,
    }


async def list_events(
    session: AsyncSession,
    *,
    child_id: int | None = None,
    from_date: date | None = None,
    to_date: date | None = None,
    include_past: bool = True,
) -> list[dict[str, Any]]:
    today = today_ist()
    q = select(KidEvent).order_by(KidEvent.start_date.asc())
    if child_id is not None:
        q = q.where(or_(KidEvent.child_id == child_id, KidEvent.child_id.is_(None)))
    if from_date is not None:
        q = q.where(KidEvent.start_date >= from_date.isoformat())
    elif not include_past:
        q = q.where(KidEvent.start_date >= today.isoformat())
    if to_date is not None:
        q = q.where(KidEvent.start_date <= to_date.isoformat())
    rows = (await session.execute(q)).scalars().all()
    return [_row_to_dict(r) for r in rows]


async def upcoming_events(
    session: AsyncSession,
    *,
    days: int = 14,
    child_id: int | None = None,
) -> list[dict[str, Any]]:
    today = today_ist()
    horizon = today + timedelta(days=days)
    return await list_events(
        session,
        child_id=child_id,
        from_date=today,
        to_date=horizon,
    )


async def upsert_event(
    session: AsyncSession, payload: dict[str, Any],
) -> dict[str, Any]:
    """Create-or-update a single event. If `id` is in payload, it's an
    edit; otherwise it's an insert."""
    event_id = payload.get("id")
    if event_id is not None:
        row = (
            await session.execute(
                select(KidEvent).where(KidEvent.id == int(event_id))
            )
        ).scalar_one_or_none()
        if row is None:
            raise ValueError(f"event {event_id} not found")
    else:
        row = KidEvent(
            title=str(payload.get("title", "")).strip(),
            start_date=str(payload.get("start_date", "")).strip(),
            source=str(payload.get("source") or "manual"),
        )
        session.add(row)

    # Required fields validation.
    if payload.get("title") is not None:
        row.title = str(payload["title"]).strip()
    if payload.get("start_date") is not None:
        row.start_date = str(payload["start_date"]).strip()
    if not row.title:
        raise ValueError("title required")
    if not row.start_date:
        raise ValueError("start_date required")
    try:
        date.fromisoformat(row.start_date)
    except Exception:
        raise ValueError(f"start_date must be ISO format YYYY-MM-DD: {row.start_date!r}")

    # Optional fields.
    for k in ("description", "end_date", "start_time", "location", "notes",
              "source_ref", "event_type"):
        if k in payload:
            v = payload[k]
            setattr(row, k, str(v).strip() if v not in ("", None) else None)
    if row.event_type and row.event_type not in VALID_TYPES:
        raise ValueError(
            f"event_type must be one of {sorted(VALID_TYPES)}, got {row.event_type!r}"
        )
    if "importance" in payload:
        try:
            row.importance = int(payload["importance"])
        except Exception:
            raise ValueError(f"importance must be int 1-3, got {payload['importance']!r}")
        row.importance = max(1, min(3, row.importance))
    if "child_id" in payload:
        cid = payload["child_id"]
        row.child_id = int(cid) if cid not in ("", None) else None

    row.updated_at = datetime.now(tz=timezone.utc)
    await session.commit()
    await session.refresh(row)
    return _row_to_dict(row)


async def delete_event(session: AsyncSession, event_id: int) -> bool:
    row = (
        await session.execute(
            select(KidEvent).where(KidEvent.id == event_id)
        )
    ).scalar_one_or_none()
    if row is None:
        return False
    await session.delete(row)
    await session.commit()
    return True


# ─── LLM extraction from school messages ────────────────────────────────────

EXTRACT_SYSTEM = """You scan a school message and extract any DATE-BOUND events worth adding to a parent's calendar.

You'll receive a single message: title + body + arrival date. Return STRICT JSON:

{
  "events": [
    {
      "title": "<short event name>",
      "event_type": "audition | competition | camp | exam | holiday | parent_meeting | trip | test | performance | deadline | other",
      "start_date": "YYYY-MM-DD",
      "end_date": "YYYY-MM-DD" | null,
      "start_time": "HH:MM" | null,
      "location": "<where>" | null,
      "importance": 1 | 2 | 3,
      "description": "<one-line summary>"
    },
    …
  ]
}

Rules:
- Output ONLY the JSON. No prose, no fences.
- If the message has NO dated event (just admin / fee / general
  reminder), return `{"events": []}`. Do not invent.
- Resolve relative dates ("tomorrow", "next Monday") using the
  message's arrival date as the anchor. If you cannot resolve a
  date confidently, OMIT that event from the list.
- importance: 3 = high stakes (audition, exam, competition); 2 =
  worth showing up for (parent meeting, school camp); 1 = nice to
  know (assembly, holiday).
- start_date in YYYY-MM-DD only. No "Apr 27", no "next Monday".
- Don't extract more than 3 events from one message.
- Skip events that have already passed (start_date < arrival_date − 60d).
"""


async def _llm_extract_events(message_title: str, message_body: str, arrival_date: str) -> list[dict[str, Any]]:
    client = LLMClient()
    if not client.enabled():
        return []
    prompt = (
        f"arrival_date: {arrival_date}\n"
        f"title: {message_title}\n"
        f"body: {message_body or '(no body)'}"
    )
    try:
        resp = await client.complete(
            purpose="kid_events_extract",
            system=EXTRACT_SYSTEM,
            prompt=prompt,
            max_tokens=512,
        )
    except Exception as e:
        log.warning("kid_events extract failed: %s", e)
        return []
    raw = (resp.text or "").strip()
    if raw.startswith("```"):
        raw = raw.split("```", 2)
        raw = raw[1] if len(raw) >= 2 else "".join(raw)
        if raw.lstrip().startswith("json"):
            raw = raw.split("\n", 1)[1] if "\n" in raw else raw
    try:
        out = json.loads(raw)
    except Exception:
        log.warning("kid_events extract returned non-JSON: %r", raw[:200])
        return []
    events = out.get("events") if isinstance(out, dict) else None
    if not isinstance(events, list):
        return []
    cleaned: list[dict[str, Any]] = []
    for e in events[:3]:
        if not isinstance(e, dict):
            continue
        try:
            sd = str(e.get("start_date", "")).strip()
            date.fromisoformat(sd)
        except Exception:
            continue
        et = str(e.get("event_type", "")).strip().lower()
        if et and et not in VALID_TYPES:
            et = "other"
        cleaned.append({
            "title": str(e.get("title", "")).strip()[:200] or "(untitled)",
            "event_type": et or "other",
            "start_date": sd,
            "end_date": str(e["end_date"]).strip() if e.get("end_date") else None,
            "start_time": str(e["start_time"]).strip() if e.get("start_time") else None,
            "location": str(e["location"]).strip() if e.get("location") else None,
            "description": str(e.get("description", "")).strip()[:500] or None,
            "importance": int(e.get("importance", 1)) if isinstance(e.get("importance"), (int, float)) else 1,
        })
    return cleaned


async def extract_from_school_messages(
    session: AsyncSession,
    *,
    days: int = 60,
    only_new: bool = True,
) -> dict[str, Any]:
    """Walk school_message rows from the last `days` days, extract any
    dated events via Claude, insert them with source='school_message'.

    Idempotent: looks up existing events by (source_ref, title) before
    inserting; same message won't double-fire.
    """
    today = today_ist()
    since = today - timedelta(days=days)
    msgs = (
        await session.execute(
            select(VeracrossItem)
            .where(VeracrossItem.kind == "school_message")
        )
    ).scalars().all()

    # Existing source_refs to dedupe against.
    existing = (
        await session.execute(
            select(KidEvent.source_ref, KidEvent.title)
            .where(KidEvent.source == "school_message")
        )
    ).all()
    existing_keys: set[tuple[str | None, str]] = {
        (r.source_ref, r.title.strip().lower()) for r in existing
    }

    scanned = 0
    extracted = 0
    inserted = 0
    skipped_dup = 0
    for m in msgs:
        d = _parse_loose_date(m.due_or_date)
        if d is None or d < since:
            continue
        if only_new:
            ref = f"school_message:{m.id}"
            if any(ref == sr for (sr, _t) in existing_keys):
                # Already extracted from this message — skip.
                continue
        scanned += 1
        body = m.body or m.title_en or ""
        events = await _llm_extract_events(
            m.title or "",
            body,
            d.isoformat(),
        )
        for e in events:
            extracted += 1
            ref = f"school_message:{m.id}"
            key = (ref, e["title"].strip().lower())
            if key in existing_keys:
                skipped_dup += 1
                continue
            try:
                await upsert_event(session, {
                    **e,
                    "source": "school_message",
                    "source_ref": ref,
                })
                existing_keys.add(key)
                inserted += 1
            except Exception as ex:
                log.warning("kid_events insert failed for %s / %s: %s", ref, e.get("title"), ex)

    return {
        "messages_scanned": scanned,
        "events_extracted": extracted,
        "events_inserted": inserted,
        "events_skipped_dup": skipped_dup,
    }
