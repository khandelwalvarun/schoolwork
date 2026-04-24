"""Background Devanagari / mojibake repair.

The light sync upserts assignments with whatever the planner gave us —
including `?????` titles for Hindi/Sanskrit rows. This task runs AFTER
the light sync returns, opens its own (quiet) scraper session, and
fetches detail pages for a small batch of mojibake items. Each success
updates the row in-place with the real Devanagari title + an LLM English
translation.

Scoped small (<= 15 items) so it never becomes a de-facto second full
sync — purely opportunistic cleanup.
"""
from __future__ import annotations

import asyncio
import logging

from sqlalchemy import select

from ..db import get_async_session
from ..models import VeracrossItem
from ..scraper.attachments import extract_and_save
from ..scraper.client import scraper_session
from ..scraper.parsers import parse_assignment_detail
from ..services.translate import needs_translation, translate_to_english
from ..scraper.sync import _now  # reuse the module's UTC now helper

log = logging.getLogger(__name__)

REPAIR_BATCH = 15
REPAIR_START_DELAY = 3.0  # seconds; let the foreground sync settle first


async def _repair_once() -> int:
    """Find mojibake rows, fetch their detail, update. Returns count repaired."""
    async with get_async_session() as session:
        rows = (
            await session.execute(
                select(VeracrossItem)
                .where(VeracrossItem.kind == "assignment")
                .where(VeracrossItem.title.like("%?%"))
                .limit(REPAIR_BATCH)
            )
        ).scalars().all()
    if not rows:
        return 0
    log.info("mojibake repair pass starting — %d rows", len(rows))

    repaired = 0
    async with scraper_session() as client:
        for r in rows:
            ext_id = None
            try:
                import json as _json
                ext_id = _json.loads(r.raw_json).get("external_id")
            except Exception:
                continue
            if not ext_id:
                continue
            detail_url = client.main_portal_url(f"/detail/assignment/{ext_id}")
            try:
                html = await client.get_html(detail_url, wait_for=".detail-assignment")
            except Exception as e:
                log.warning("repair fetch failed %s: %s", ext_id, e)
                continue
            try:
                d = parse_assignment_detail(html)
                new_title = d.get("title")
                new_notes = d.get("notes")
            except Exception as e:
                log.warning("repair parse failed %s: %s", ext_id, e)
                continue
            async with get_async_session() as session:
                item = (
                    await session.execute(select(VeracrossItem).where(VeracrossItem.id == r.id))
                ).scalar_one_or_none()
                if item is None:
                    continue
                changed = False
                if new_title and "?" not in new_title and new_title != item.title:
                    item.title = new_title
                    changed = True
                if (
                    new_title and needs_translation(new_title)
                    and not item.title_en
                ):
                    t_en = await translate_to_english(new_title)
                    if t_en and t_en != new_title:
                        item.title_en = t_en
                        changed = True
                if (
                    new_notes and needs_translation(new_notes)
                    and not item.notes_en
                ):
                    n_en = await translate_to_english(new_notes)
                    if n_en and n_en != new_notes:
                        item.notes_en = n_en
                        changed = True
                item.detail_fetched_at = _now()
                await session.commit()
                if changed:
                    repaired += 1
                    log.info("repaired: %s → %r", ext_id, new_title)
                # Also save any attachments we noticed
                try:
                    await extract_and_save(
                        session, client, item_id=item.id, child_id=item.child_id,
                        detail_html=html, source_kind="assignment",
                    )
                    await session.commit()
                except Exception as e:
                    log.warning("repair attachment save failed %s: %s", ext_id, e)
    return repaired


async def repair_mojibake_background() -> None:
    """Entrypoint for fire-and-forget asyncio.create_task — logs errors
    rather than propagating."""
    try:
        await asyncio.sleep(REPAIR_START_DELAY)
        n = await _repair_once()
        if n:
            log.info("mojibake repair done: %d repaired", n)
    except asyncio.CancelledError:
        raise
    except Exception:
        log.exception("mojibake repair aborted")
