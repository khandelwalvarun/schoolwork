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
    from ..util.time import today_iso_ist
    return today_iso_ist()


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

    # `normalized["body"]` is the parsed homework description from the
    # assignment-detail popup (Veracross "Notes"). Persist as a column so
    # the UI can render it without re-parsing JSON. We only treat it as a
    # real body when it's distinct from the title — otherwise the value is
    # just a fallback the enrichment branch wrote.
    body_val = normalized.get("body") if isinstance(normalized, dict) else None
    if body_val and isinstance(body_val, str):
        body_val = body_val.strip() or None
        if body_val and body_val == (title or "").strip():
            body_val = None

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
            body=body_val,
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
    # Update body when a richer one arrives. Rules in priority order:
    #   1. existing is empty → take it
    #   2. new is longer → take it
    #   3. same length AND new has fewer `?`s → mojibake repair (the planner
    #      serves Devanagari as same-count `?`s; the clean detail-page parse
    #      replaces it)
    #   4. existing is mostly `?`s and new has fewer → repair
    if body_val:
        existing_body = existing.body or ""
        new_q = body_val.count("?")
        old_q = existing_body.count("?")
        if (
            not existing_body
            or len(body_val) > len(existing_body)
            or (len(body_val) == len(existing_body) and new_q < old_q)
            or (new_q < old_q and old_q > len(existing_body) // 2)
        ):
            existing.body = body_val
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
    force_rediscover: bool = False,
) -> None:
    today_iso = _today_iso()
    # Prefer the cache; only re-probe Veracross when cache missing/stale or
    # the caller forced a rediscover (heavy tier).
    from ..services import veracross_cache as vc_cache
    cached = vc_cache.get_for_child(child.id)
    discovered: list[int] = []
    if cached and not force_rediscover and not vc_cache.is_stale(child.id):
        discovered = list(cached.get("grading_periods") or [])
        log.info("child=%s grading periods from cache: %s", child.display_name, discovered)
    else:
        if child.veracross_id and classes:
            for cls in classes:
                cid = cls.get("class_id")
                if cid:
                    discovered = await _discover_grading_periods(
                        client, child.veracross_id, cid
                    )
                    if discovered:
                        break
        if discovered:
            # Persist — also refresh the class list since we had to probe anyway
            try:
                vc_cache.set_for_child(
                    child_pk=child.id,
                    vc_id=child.veracross_id or "",
                    class_ids=[c["class_id"] for c in classes if c.get("class_id")],
                    grading_periods=discovered,
                )
                log.info("cached grading periods for %s: %s", child.display_name, discovered)
            except Exception as e:
                log.warning("couldn't update cache: %s", e)
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
    tier: str = "medium",
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
    # Tier-aware detail-fetch scope:
    #  light:   NEW items only (mojibake repair deferred to background task)
    #  medium:  NEW + items whose detail_fetched_at is NULL or >24h old
    #  heavy:   NEW + EVERYTHING (full rebuild)
    from datetime import timedelta
    now_ts = _now()
    stale_cutoff = now_ts - timedelta(hours=24)

    priority: list[tuple[str, int]] = []
    backfill: list[tuple[str, int]] = []
    mojibake_ids: set[int] = set()

    if tier in ("medium", "heavy"):
        mojibake_rows = (
            await session.execute(
                select(VeracrossItem.id, VeracrossItem.external_id)
                .where(VeracrossItem.kind == "assignment")
                .where(VeracrossItem.child_id == child.id)
                .where(VeracrossItem.title.like("%?%"))
            )
        ).all()
        for iid, ext_id in mojibake_rows:
            if iid not in in_scope_ids:
                priority.append((ext_id, iid))
                mojibake_ids.add(iid)

        # Staleness-aware backfill: items never detail-fetched, or not in >24h.
        stale_q = select(
            VeracrossItem.id, VeracrossItem.external_id, VeracrossItem.detail_fetched_at
        ).where(VeracrossItem.kind == "assignment").where(VeracrossItem.child_id == child.id)
        if tier == "medium":
            # Items whose detail_fetched_at is null OR older than 24h
            from sqlalchemy import or_
            stale_q = stale_q.where(
                or_(
                    VeracrossItem.detail_fetched_at.is_(None),
                    VeracrossItem.detail_fetched_at < stale_cutoff,
                )
            )
        # heavy: no filter — re-fetch everything
        stale_rows = (await session.execute(stale_q)).all()
        for iid, ext_id, _dfa in stale_rows:
            if iid not in items_with_att and iid not in in_scope_ids and iid not in mojibake_ids:
                backfill.append((ext_id, iid))

    # light: only new_or_active (the planner-fresh ones)
    combined = list(new_or_active_items) + priority + backfill
    cap = 80 if tier == "heavy" else (40 if tier == "medium" else 15)
    if extract_and_save is not None and combined:
        combined = combined[:cap]
        from ..services.translate import needs_translation, translate_to_english
        for ext_id, item_id in combined:
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
                    # Stamp successful detail fetch so future light/medium
                    # syncs can skip this item.
                    item_row.detail_fetched_at = _now()
                    # Persist the parsed detail object back into raw_json
                    # so downstream consumers (homework_load, sunday_brief,
                    # any future analytics) can read date_assigned / weight /
                    # max_score / notes without re-fetching. The enrichment
                    # branch already does this, but the planner-only +
                    # back-fill path was dropping everything except the
                    # specific fields it explicitly mapped.
                    try:
                        existing_raw = json.loads(item_row.raw_json or "{}")
                    except Exception:
                        existing_raw = {}
                    if isinstance(existing_raw, dict):
                        prev_detail = existing_raw.get("detail") or {}
                        # Merge — new keys overwrite old, but don't drop
                        # anything the existing payload already had.
                        merged_detail = {**prev_detail, **{k: v for k, v in d.items() if v is not None}}
                        if merged_detail != prev_detail:
                            existing_raw["detail"] = merged_detail
                            item_row.raw_json = json.dumps(
                                existing_raw, default=str, ensure_ascii=False,
                            )
                            changed_any = True
                    # Also lift date_assigned / weight / max_score into
                    # normalized_json so consumers don't have to dig
                    # through raw_json["detail"].
                    try:
                        norm = json.loads(item_row.normalized_json or "{}")
                    except Exception:
                        norm = {}
                    if isinstance(norm, dict):
                        norm_changed = False
                        for k in ("date_assigned", "weight", "max_score", "type", "teacher"):
                            v = d.get(k)
                            if v and norm.get(k) != v:
                                norm[k] = v
                                norm_changed = True
                        if norm_changed:
                            item_row.normalized_json = json.dumps(
                                norm, default=str, ensure_ascii=False,
                            )
                            changed_any = True
                    # Persist the description body — UNCONDITIONALLY, not
                    # gated on translation. The translator path only ran
                    # for non-Latin notes, so English bodies were silently
                    # discarded. We now keep the original on `body`; the
                    # translation, if any, lands on `notes_en` separately.
                    if detail_notes:
                        body_clean = detail_notes.strip()
                        if body_clean and body_clean != (item_row.title or "").strip():
                            existing = item_row.body or ""
                            new_q = body_clean.count("?")
                            old_q = existing.count("?")
                            # Same length, fewer ?s → mojibake repair
                            #   (planner-encoded Devanagari arrives as `?`s of
                            #   identical character count to the clean Devanagari
                            #   from the detail page, so the old "longer wins"
                            #   rule wouldn't replace).
                            # Empty / longer / cleaner → write.
                            if (
                                not existing
                                or len(body_clean) > len(existing)
                                or (len(body_clean) == len(existing) and new_q < old_q)
                                or (new_q < old_q and old_q > len(existing) // 2)
                            ):
                                item_row.body = body_clean
                                changed_any = True
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
            force_rediscover=(tier == "heavy"),
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


# Module-level lock: only one sync may execute in-process at a time.
# The APScheduler hourly_sync job has max_instances=1, but that doesn't
# stop manual POST /api/sync from overlapping the cron. This lock does.
_SYNC_LOCK: asyncio.Lock = asyncio.Lock()
STALE_RUN_MIN = 15  # any "running" row older than this is treated as orphaned


async def _cleanup_stale_runs(older_than_min: int = STALE_RUN_MIN) -> int:
    """Mark any row stuck at status='running' as failed.

    Called in two places:
      - FastAPI lifespan startup (older_than_min=0 → close every 'running'
        row, because no new sync has started yet in this process so anything
        that still says running IS an orphan from the previous lifetime).
      - Before each run_sync (default STALE_RUN_MIN minutes — only closes
        rows that have been running impossibly long, so a legitimate
        in-flight sync isn't clobbered).
    """
    from datetime import timedelta
    if older_than_min <= 0:
        cutoff = _now() + timedelta(seconds=1)  # any started_at is "before" this
    else:
        cutoff = _now() - timedelta(minutes=older_than_min)
    closed = 0
    async with get_async_session() as session:
        stale = (
            await session.execute(
                select(SyncRun).where(SyncRun.status == "running").where(SyncRun.started_at < cutoff)
            )
        ).scalars().all()
        for r in stale:
            r.status = "failed"
            r.ended_at = _now()
            r.error = (r.error or "") + "orphaned: process exited before run completed"
            closed += 1
        if closed:
            await session.commit()
            log.warning("closed %d stale running sync_run rows", closed)
    return closed


async def run_sync(
    trigger: str = "manual",
    tier: str = "light",
    include_grades: bool | None = None,
    grading_periods: tuple[int, ...] | None = None,
) -> dict[str, Any]:
    """Orchestrate one sync pass. Returns a summary dict.

    Tiered:
      light:   hourly — planner + messages + detail fetch for NEW items
               only. No grade probing. Mojibake repair runs as a background
               task AFTER this returns.
      medium:  daily — light + grades (using cached periods) + attachment
               repair pass for items whose detail_fetched_at is null/stale.
      heavy:   weekly — medium + grading-period rediscovery +
               class-roster revalidation + full attachment re-fetch.

    Serialised: only one sync executes at a time. If called while another
    is running, the overlap is refused with status='skipped_concurrent'.

    Legacy `include_grades=True` forces medium behaviour (kept for back-compat).
    """
    from ..config import get_settings
    s = get_settings()
    if grading_periods is None:
        grading_periods = (s.grading_period_current,)

    # Back-compat shim: if caller passed include_grades explicitly, use it
    # to pick a tier. Otherwise honour the `tier` argument.
    if include_grades is True and tier == "light":
        tier = "medium"
    resolved_include_grades = tier in ("medium", "heavy")

    # Concurrency guard: refuse overlapping in-process calls.
    if _SYNC_LOCK.locked():
        log.warning("sync refused: another run is already in progress (trigger=%s tier=%s)",
                    trigger, tier)
        return {
            "sync_run_id": None,
            "status": "skipped_concurrent",
            "trigger": trigger,
            "tier": tier,
            "error": "another sync is already running",
        }

    # Housekeeping: any row stuck at running from a previous crash.
    try:
        await _cleanup_stale_runs()
    except Exception:
        log.exception("stale-run cleanup failed (non-fatal)")

    async with _SYNC_LOCK:
        return await _run_sync_locked(trigger, tier, resolved_include_grades, grading_periods)


async def _run_sync_locked(
    trigger: str,
    tier: str,
    include_grades: bool,
    grading_periods: tuple[int, ...],
) -> dict[str, Any]:
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

    # Attach a memory log handler so we can persist the run log to the DB
    # for the Settings → sync log viewer. Limited to 200KB per run; anything
    # more gets truncated. Handler is detached in the finally block.
    import io, logging as _logging, time as _time
    from ..util.time import IST as _IST
    log_buffer = io.StringIO()
    formatter = _logging.Formatter("%(asctime)s IST  %(levelname)-5s  %(name)s: %(message)s", "%H:%M:%S")
    # Force log records to stamp IST, not the server's local zone.
    def _ist_converter(secs: float | None) -> _time.struct_time:
        from datetime import datetime as _dt
        return _dt.fromtimestamp(secs or 0, tz=_IST).timetuple()
    formatter.converter = _ist_converter  # type: ignore[assignment]
    buf_handler = _logging.StreamHandler(log_buffer)
    buf_handler.setLevel(_logging.INFO)
    buf_handler.setFormatter(formatter)
    capture_loggers = [
        _logging.getLogger("backend.app.scraper.sync"),
        _logging.getLogger("backend.app.scraper.client"),
        _logging.getLogger("backend.app.scraper.attachments"),
        _logging.getLogger("backend.app.notability.dispatcher"),
        _logging.getLogger("backend.app.notability.engine"),
        _logging.getLogger("backend.app.services.translate"),
    ]
    for lg in capture_loggers:
        lg.addHandler(buf_handler)
    # Sentinel — lets the frontend confirm log capture plumbing is intact
    # even when the sync itself was a no-op.
    log.info("=== sync started (id=%s trigger=%s tier=%s include_grades=%s) ===",
             sync_run_id, trigger, tier, include_grades)

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
                            tier=tier,
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

    # Sentinel — so we can verify capture is intact end-to-end
    log.info("=== sync ended (status=%s new=%s updated=%s events=%s) ===",
             ("failed" if err else ("partial" if counters.get("errors") else "ok")),
             counters["items_new"], counters["items_updated"], counters["events_produced"])

    # Detach log capture, clip to a sane size for the DB column
    for lg in capture_loggers:
        try:
            lg.removeHandler(buf_handler)
        except Exception:
            pass
    captured = log_buffer.getvalue()
    if len(captured) > 200_000:
        captured = (
            captured[:100_000]
            + "\n\n…[truncated]…\n\n"
            + captured[-90_000:]
        )
    log_buffer.close()

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
        run.log_text = captured or None
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
