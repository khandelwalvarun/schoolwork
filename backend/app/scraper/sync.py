"""Sync orchestrator. Walks the portal, upserts veracross_items, records a sync_run.

Callable from:
  * FastAPI /api/sync endpoint
  * MCP trigger_sync tool
  * APScheduler hourly job (future)
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_async_session
from ..models import Child, SyncRun, VeracrossItem
from ..notability.dispatcher import dispatch_event
from ..notability.engine import (
    DiffAggregator,
    ItemDiff,
    compute_aggregate_events,
    compute_events,
    persist_events,
)
from .client import ScraperClient, scraper_session
from .parsers import (
    parse_assignment_detail,
    parse_email_detail,
    parse_grade_report,
    parse_messages_list,
    parse_planner,
    status_from_badge,
)

log = logging.getLogger(__name__)


def _now() -> datetime:
    return datetime.now(tz=timezone.utc)


def _today_iso() -> str:
    return date.today().isoformat()


async def _upsert_item(
    session: AsyncSession,
    *,
    child_id: int,
    kind: str,
    external_id: str,
    subject: str | None,
    title: str | None,
    due_or_date: str | None,
    status: str | None,
    raw: Any,
    normalized: dict[str, Any],
    diff: DiffAggregator | None = None,
) -> tuple[bool, bool, int | None]:
    """Upsert by (child_id, kind, external_id). Returns (is_new, is_changed, item_id).
    If `diff` provided, records an ItemDiff for event production."""
    existing = (
        await session.execute(
            select(VeracrossItem).where(
                VeracrossItem.child_id == child_id,
                VeracrossItem.kind == kind,
                VeracrossItem.external_id == external_id,
            )
        )
    ).scalar_one_or_none()

    now = _now()
    raw_s = json.dumps(raw, default=str, ensure_ascii=False)
    norm_s = json.dumps(normalized, default=str, ensure_ascii=False)

    if existing is None:
        item = VeracrossItem(
            child_id=child_id,
            kind=kind,
            external_id=external_id,
            subject=subject,
            title=title,
            due_or_date=due_or_date,
            raw_json=raw_s,
            normalized_json=norm_s,
            status=status,
            first_seen_at=now,
            last_seen_at=now,
        )
        session.add(item)
        await session.flush()
        if diff is not None:
            diff.record(
                ItemDiff(
                    kind=kind, child_id=child_id, external_id=external_id,
                    is_new=True, old_status=None, new_status=status,
                    title=title, subject=subject, due_or_date=due_or_date,
                    item_id=item.id,
                    parent_marked_submitted=False,
                )
            )
        return True, False, item.id

    old_status = existing.status
    # DON'T downgrade a clean title to a mojibake one. The planner feed serves
    # Hindi/Sanskrit titles as '?' placeholders; if we already have a good
    # Devanagari value (refreshed from the detail page), keep it.
    incoming_title_has_mojibake = bool(title) and "?" in (title or "")
    stored_title_clean = bool(existing.title) and "?" not in (existing.title or "")
    if incoming_title_has_mojibake and stored_title_clean:
        title = existing.title  # preserve clean title
    changed = (
        existing.subject != subject
        or existing.title != title
        or existing.due_or_date != due_or_date
        or existing.status != status
        or existing.normalized_json != norm_s
    )
    existing.subject = subject
    existing.title = title
    existing.due_or_date = due_or_date
    existing.status = status
    existing.raw_json = raw_s
    existing.normalized_json = norm_s
    existing.last_seen_at = now
    parent_marked = existing.parent_marked_submitted_at is not None
    if diff is not None and (changed or (old_status != status)):
        diff.record(
            ItemDiff(
                kind=kind, child_id=child_id, external_id=external_id,
                is_new=False, old_status=old_status, new_status=status,
                title=title, subject=subject, due_or_date=due_or_date,
                item_id=existing.id,
                parent_marked_submitted=parent_marked,
            )
        )
    # Also fire overdue-threshold events even on unchanged items if they've crossed
    # a day boundary since the last sync; the dedup_key guards re-firing.
    elif diff is not None and kind == "assignment":
        diff.record(
            ItemDiff(
                kind=kind, child_id=child_id, external_id=external_id,
                is_new=False, old_status=old_status, new_status=status,
                title=title, subject=subject, due_or_date=due_or_date,
                item_id=existing.id,
                parent_marked_submitted=parent_marked,
            )
        )
    return False, changed, existing.id


async def _discover_grading_periods(
    client: ScraperClient, child_vc_id: str, class_id: str
) -> list[int]:
    """Veracross grading-period IDs differ per tier (MS=13, JS=25/27/31/33, etc.).
    We read the parent-portal enrollment page for one class and pull out every
    `grading_period=N` value we see."""
    import re as _re
    url = client.enrollment_grade_detail_url(child_vc_id, class_id)
    try:
        html = await client.get_html(url, wait_for="body")
    except Exception as e:
        log.warning("enrollment page fetch failed for %s: %s", class_id, e)
        return []
    periods = sorted({int(m) for m in _re.findall(r"grading_period=(\d+)", html)})
    return periods


async def _sync_grades_for_child(
    session: AsyncSession,
    client: ScraperClient,
    child: Child,
    classes: list[dict[str, Any]],
    grading_periods: tuple[int, ...],
    counters: dict[str, int],
    diff: DiffAggregator,
) -> None:
    today_iso = _today_iso()
    # Discover real grading periods for this child, once, from the first class.
    discovered: list[int] = []
    if child.veracross_id and classes:
        for cls in classes:
            cid = cls.get("class_id")
            if cid:
                discovered = await _discover_grading_periods(
                    client, child.veracross_id, cid
                )
                if discovered:
                    break
    periods_to_fetch: tuple[int, ...] = tuple(discovered) if discovered else grading_periods
    log.info(
        "child=%s grading periods used: %s (hardcoded fallback: %s)",
        child.display_name, periods_to_fetch, grading_periods,
    )
    for cls in classes:
        class_id = cls.get("class_id")
        subject = cls.get("subject")
        teacher = cls.get("teacher")
        if not class_id:
            continue
        for period in periods_to_fetch:
            url = client.grade_report_url(class_id, period)
            try:
                html = await client.get_html(url, wait_for="body")
                parsed = parse_grade_report(html, class_id, period)
            except Exception as e:
                log.warning("grade fetch failed for %s p=%d: %s", class_id, period, e)
                continue
            for g in parsed["grades"]:
                # Use class_id + period + due_date + assignment prefix as stable external id.
                is_new, is_changed, _ = await _upsert_item(
                    session,
                    child_id=child.id,
                    kind="grade",
                    external_id=g["external_id"],
                    subject=subject,
                    title=g.get("assignment"),
                    due_or_date=g.get("due_date"),
                    status="graded" if g.get("grade_pct") is not None else "posted",
                    raw=g,
                    normalized={
                        "teacher": teacher,
                        "assignment_type": g.get("assignment_type"),
                        "grade_pct": g.get("grade_pct"),
                        "points_earned": g.get("points_earned"),
                        "points_possible": g.get("points_possible"),
                        "score_text": g.get("score_text"),
                        "grading_period": period,
                        "class_id": class_id,
                        "body": f"{g.get('assignment','')} — {g.get('score_text','')} ({g.get('grade_pct','?')}%)",
                    },
                    diff=diff,
                )
                if is_new:
                    counters["items_new"] += 1
                elif is_changed:
                    counters["items_updated"] += 1


async def _sync_one_child(
    session: AsyncSession,
    client: ScraperClient,
    child: Child,
    counters: dict[str, int],
    diff: DiffAggregator,
    include_grades: bool = True,
    grading_periods: tuple[int, ...] = (21,),
) -> None:
    if not child.veracross_id:
        log.warning("child %s has no veracross_id", child.display_name)
        return

    planner_url = client.embed_planner_url(child.veracross_id)
    log.info("fetch planner: %s", planner_url)
    html = await client.get_html(planner_url, wait_for=".assignment, .timeline-row")
    planner = parse_planner(html, child.veracross_id, assume_year=datetime.now().year)

    today_iso = _today_iso()

    # Track which assignments need a detail fetch for attachment download.
    new_or_active_items: list[tuple[str, int]] = []  # (external_id, item_id)

    for a in planner["assignments"]:
        status = status_from_badge(a.get("status_badge"), a.get("due_date"), today_iso)
        is_new, is_changed, item_id = await _upsert_item(
            session,
            child_id=child.id,
            kind="assignment",
            external_id=a["external_id"],
            subject=a.get("subject"),
            title=a.get("title"),
            due_or_date=a.get("due_date"),
            status=status,
            raw=a,
            normalized={
                "type": a.get("type"),
                "teacher": a.get("teacher"),
                "body": a.get("title") or "",
                "status_badge": a.get("status_badge"),
            },
            diff=diff,
        )
        if is_new:
            counters["items_new"] += 1
        elif is_changed:
            counters["items_updated"] += 1
        # Fetch detail (→ attachments) for every new item AND any still-open one
        # whose due is upcoming / recently overdue, so attachments added late
        # still land on disk.
        due = a.get("due_date")
        open_enough = status not in ("submitted", "graded", "dismissed")
        if item_id is not None and (is_new or (open_enough and due and due >= today_iso)):
            new_or_active_items.append((a["external_id"], item_id))

    to_enrich = [
        a for a in planner["assignments"]
        if not a.get("subject") or not a.get("due_date")
    ]
    for a in to_enrich[:40]:
        detail_url = client.main_portal_url(f"/detail/assignment/{a['external_id']}")
        try:
            detail_html = await client.get_html(detail_url, wait_for=".detail-assignment")
            d = parse_assignment_detail(detail_html)
        except Exception as e:
            log.warning("detail fetch failed for %s: %s", a["external_id"], e)
            continue
        subject = a.get("subject") or d.get("subject")
        due = a.get("due_date")
        if not due and d.get("due_date"):
            from .parsers import _parse_long_date
            dt = _parse_long_date(d["due_date"], datetime.now().year)
            due = dt.isoformat() if dt else None
        status = status_from_badge(a.get("status_badge"), due, today_iso)
        merged = {**a, "detail": d, "subject": subject, "due_date": due}
        _, is_changed, _ = await _upsert_item(
            session,
            child_id=child.id,
            kind="assignment",
            external_id=a["external_id"],
            subject=subject,
            title=a.get("title") or d.get("title"),
            due_or_date=due,
            status=status,
            raw=merged,
            normalized={
                "type": a.get("type") or d.get("type"),
                "teacher": a.get("teacher") or d.get("teacher"),
                "body": d.get("notes") or a.get("title") or "",
                "date_assigned": d.get("date_assigned"),
                "max_score": d.get("max_score"),
                "weight": d.get("weight"),
            },
            diff=diff,
        )
        if is_changed:
            counters["items_updated"] += 1

    # ── Attachment pass: fetch assignment-detail pages and download any linked
    # files. Covers (a) newly created items, (b) still-open upcoming/due items,
    # and (c) a back-fill of anything that doesn't yet have an attachment row
    # attached. Rate-limited to a sane cap per sync.
    try:
        from .attachments import extract_and_save
    except Exception as _e:
        log.warning("attachments module unavailable: %s", _e)
        extract_and_save = None  # type: ignore[assignment]

    # Back-fill: any assignment for this child without a recorded attachment
    # row gets its detail fetched at least once. We don't re-fetch items that
    # already have an attachment row attached.
    from ..models import Attachment, VeracrossItem
    already_have_attachments_q = (
        select(VeracrossItem.id, VeracrossItem.external_id)
        .where(VeracrossItem.kind == "assignment")
        .where(VeracrossItem.child_id == child.id)
    )
    all_items = (await session.execute(already_have_attachments_q)).all()
    items_with_att = set(
        r[0] for r in (
            await session.execute(
                select(Attachment.item_id)
                .where(Attachment.item_id.in_([i[0] for i in all_items] or [0]))
            )
        ).all()
    )
    in_scope_ids = {iid for ext, iid in new_or_active_items}
    # Priority: any row whose title still has '?' placeholders (Devanagari
    # mojibake) OR has no attachment yet.
    mojibake_ids: set[int] = set()
    mojibake_rows = (
        await session.execute(
            select(VeracrossItem.id, VeracrossItem.external_id)
            .where(VeracrossItem.kind == "assignment")
            .where(VeracrossItem.child_id == child.id)
            .where(VeracrossItem.title.like("%?%"))
        )
    ).all()
    priority: list[tuple[str, int]] = []
    for iid, ext_id in mojibake_rows:
        if iid not in in_scope_ids:
            priority.append((ext_id, iid))
            mojibake_ids.add(iid)
    backfill: list[tuple[str, int]] = [
        (ext_id, iid) for (iid, ext_id) in all_items
        if iid not in items_with_att
        and iid not in in_scope_ids
        and iid not in mojibake_ids
    ]
    combined = list(new_or_active_items) + priority + backfill
    if extract_and_save is not None and combined:
        from ..services.translate import needs_translation, translate_to_english
        for ext_id, item_id in combined[:80]:
            detail_url = client.main_portal_url(f"/detail/assignment/{ext_id}")
            try:
                detail_html = await client.get_html(detail_url, wait_for=".detail-assignment")
            except Exception as e:
                log.warning("attachment detail fetch failed for %s: %s", ext_id, e)
                continue
            # Refresh title / subject from the detail page — the main-portal
            # detail HTML preserves Devanagari bytes, unlike the embed planner
            # which serves them as '?'.
            try:
                d = parse_assignment_detail(detail_html)
                detail_title = d.get("title")
                detail_notes = d.get("notes")
                item_row = (
                    await session.execute(
                        select(VeracrossItem).where(VeracrossItem.id == item_id)
                    )
                ).scalar_one_or_none()
                if item_row is not None:
                    changed_any = False
                    # Prefer detail title if it has fewer placeholder '?'s
                    if detail_title and (
                        (item_row.title or "").count("?") > detail_title.count("?")
                        or item_row.title != detail_title
                    ):
                        item_row.title = detail_title
                        changed_any = True
                    # Translate if non-Latin, only if title_en is empty or stale
                    if (
                        detail_title
                        and needs_translation(detail_title)
                        and (not item_row.title_en or item_row.title_en == "")
                    ):
                        try:
                            t_en = await translate_to_english(detail_title)
                            if t_en and t_en != detail_title:
                                item_row.title_en = t_en
                                changed_any = True
                        except Exception as _e:
                            log.warning("translate title failed %s: %s", ext_id, _e)
                    if (
                        detail_notes
                        and needs_translation(detail_notes)
                        and not item_row.notes_en
                    ):
                        try:
                            n_en = await translate_to_english(detail_notes)
                            if n_en and n_en != detail_notes:
                                item_row.notes_en = n_en
                                changed_any = True
                        except Exception as _e:
                            log.warning("translate notes failed %s: %s", ext_id, _e)
                    if changed_any:
                        counters["items_updated"] += 1
                        await session.flush()
            except Exception as e:
                log.warning("detail refresh failed for %s: %s", ext_id, e)
            try:
                n = await extract_and_save(
                    session, client, item_id=item_id, child_id=child.id,
                    detail_html=detail_html, source_kind="assignment",
                )
                if n:
                    counters.setdefault("attachments_downloaded", 0)
                    counters["attachments_downloaded"] += n
            except Exception as e:
                log.warning("attachment save failed for %s: %s", ext_id, e)

    if include_grades:
        await _sync_grades_for_child(
            session=session,
            client=client,
            child=child,
            classes=planner["classes"],
            grading_periods=grading_periods,
            counters=counters,
            diff=diff,
        )


async def _sync_messages(
    session: AsyncSession,
    client: ScraperClient,
    counters: dict[str, int],
    diff: DiffAggregator,
) -> None:
    """School-wide messages — no child_id attached; attach to both kids for now so
    they show in each child's feed, OR store with child_id=NULL. The data model
    allows NULL on events but not on items — use the first child as owner and
    flag kind='school_message' so the UI can scope correctly.

    We use the first seeded child as the 'owner' purely for the FK; the UI treats
    school_message kind as family-wide.
    """
    owner = (
        await session.execute(select(Child).order_by(Child.id).limit(1))
    ).scalar_one_or_none()
    if owner is None:
        return

    list_url = client.main_portal_url("/messages")
    html = await client.get_html(list_url, wait_for=".vx-list__item.message, .vx-list__item")
    rows = parse_messages_list(html, base_url=client.main_portal_url("/"))
    for row in rows:
        is_new, is_changed, _ = await _upsert_item(
            session,
            child_id=owner.id,
            kind="school_message",
            external_id=row["external_id"],
            subject=row.get("category"),
            title=row.get("subject"),
            due_or_date=row.get("date_sent"),
            status="new" if row.get("date_sent") else None,
            raw=row,
            normalized={
                "from": row.get("from"),
                "from_label": row.get("from_label"),
                "body": row.get("subject") or "",
                "detail_url": row.get("detail_url"),
            },
            diff=diff,
        )
        if is_new:
            counters["items_new"] += 1
        elif is_changed:
            counters["items_updated"] += 1

        if is_new and row.get("detail_url"):
            try:
                detail_html = await client.get_html(
                    row["detail_url"], wait_for=".vx-record-title, .detail-email"
                )
                e = parse_email_detail(detail_html)
                _is_new2, _ch2, msg_item_id = await _upsert_item(
                    session,
                    child_id=owner.id,
                    kind="school_message",
                    external_id=row["external_id"],
                    subject=row.get("category"),
                    title=e.get("title") or row.get("subject"),
                    due_or_date=e.get("sent") or row.get("date_sent"),
                    status="new",
                    raw={**row, "detail": e},
                    normalized={
                        "from": e.get("from") or row.get("from"),
                        "body": e.get("body") or row.get("subject") or "",
                        "to": e.get("to"),
                        "detail_url": row.get("detail_url"),
                    },
                    diff=None,
                )
                # Download any files linked in the message body.
                if msg_item_id is not None:
                    try:
                        from .attachments import extract_and_save
                        n = await extract_and_save(
                            session, client, item_id=msg_item_id, child_id=owner.id,
                            detail_html=detail_html, source_kind="school_message",
                        )
                        if n:
                            counters.setdefault("attachments_downloaded", 0)
                            counters["attachments_downloaded"] += n
                    except Exception as exc:
                        log.warning("message attachments failed for %s: %s", row["external_id"], exc)
            except Exception as exc:
                log.warning("message detail failed for %s: %s", row["external_id"], exc)


async def run_sync(
    trigger: str = "manual",
    include_grades: bool = True,
    grading_periods: tuple[int, ...] | None = None,
) -> dict[str, Any]:
    """Orchestrate one sync pass. Returns a summary dict.

    `include_grades=True` adds a grade-report scan (one request per class per
    grading period). Keep off by default for hourly syncs; enable weekly or
    on-demand.
    """
    from ..config import get_settings
    s = get_settings()
    if grading_periods is None:
        grading_periods = (s.grading_period_current,)

    counters = {
        "items_new": 0,
        "items_updated": 0,
        "events_produced": 0,
        "notifications_fired": 0,
    }
    started = _now()
    sync_run_id: int | None = None
    err: str | None = None

    # Step 1: open sync_run row
    async with get_async_session() as session:
        run = SyncRun(started_at=started, trigger=trigger, status="running")
        session.add(run)
        await session.commit()
        await session.refresh(run)
        sync_run_id = run.id

    diff = DiffAggregator()
    event_ids: list[int] = []

    try:
        async with scraper_session() as client:
            async with get_async_session() as session:
                children = (
                    await session.execute(select(Child).order_by(Child.id))
                ).scalars().all()
                for child in children:
                    try:
                        await _sync_one_child(
                            session, client, child, counters, diff,
                            include_grades=include_grades,
                            grading_periods=grading_periods,
                        )
                        await session.commit()
                    except Exception as e:
                        log.exception("sync failed for child %s", child.display_name)
                        counters.setdefault("errors", 0)
                        counters["errors"] += 1
                        await session.rollback()

                try:
                    await _sync_messages(session, client, counters, diff)
                    await session.commit()
                except Exception as e:
                    log.exception("messages sync failed")
                    counters.setdefault("errors", 0)
                    counters["errors"] += 1
                    await session.rollback()

                # Event production + dispatch.
                try:
                    packed = compute_events(diff)
                    agg = await compute_aggregate_events(session, diff)
                    all_packed = packed + agg
                    if all_packed:
                        await persist_events(session, all_packed)
                        await session.commit()
                        counters["events_produced"] = len(all_packed)

                        # Find IDs for events whose dedup_key was inserted in this pass.
                        from ..models import Event
                        rows = (
                            await session.execute(
                                select(Event.id, Event.dedup_key)
                                .where(Event.dedup_key.in_([p["dedup_key"] for p in all_packed]))
                            )
                        ).all()
                        event_ids = [r.id for r in rows]
                except Exception:
                    log.exception("event production failed")
                    counters.setdefault("errors", 0)
                    counters["errors"] += 1

                # Dispatch each event through the channel policy.
                for eid in event_ids:
                    try:
                        results = await dispatch_event(session, eid)
                        counters["notifications_fired"] += sum(
                            1 for r in results if r.status == "sent"
                        )
                    except Exception:
                        log.exception("dispatch failed for event %s", eid)
    except Exception as e:
        err = repr(e)
        log.exception("sync aborted")

    ended = _now()

    # Step 2: close sync_run row
    async with get_async_session() as session:
        run = (
            await session.execute(select(SyncRun).where(SyncRun.id == sync_run_id))
        ).scalar_one()
        run.ended_at = ended
        run.status = "failed" if err else ("partial" if counters.get("errors") else "ok")
        run.items_new = counters["items_new"]
        run.items_updated = counters["items_updated"]
        run.events_produced = counters["events_produced"]
        run.notifications_fired = counters["notifications_fired"]
        run.error = err
        await session.commit()

    return {
        "sync_run_id": sync_run_id,
        "status": "failed" if err else ("partial" if counters.get("errors") else "ok"),
        "started_at": started.isoformat(),
        "ended_at": ended.isoformat(),
        "duration_sec": (ended - started).total_seconds(),
        **counters,
        "error": err,
    }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    result = asyncio.run(run_sync(trigger="cli"))
    print(json.dumps(result, indent=2, default=str))
