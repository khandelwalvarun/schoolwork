"""APScheduler entry points for the three sync tiers.

  light  (hourly)  — planner + messages only; post-sync background task
                     repairs Devanagari titles.
  medium (daily)   — light + grades (using cached periods) + attachment
                     repair for items with stale detail_fetched_at.
  heavy  (weekly)  — medium + grading-period rediscovery + class-roster
                     revalidation + full attachment re-fetch + syllabus
                     recheck.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from ..scraper.sync import run_sync

log = logging.getLogger(__name__)


async def _run_tier(tier: str, trigger: str) -> dict[str, Any]:
    try:
        result = await run_sync(trigger=trigger, tier=tier)
        log.info(
            "%s sync done: status=%s new=%d updated=%d events=%d fired=%d",
            tier, result.get("status"),
            result.get("items_new", 0), result.get("items_updated", 0),
            result.get("events_produced", 0), result.get("notifications_fired", 0),
        )
        return result
    except Exception:
        log.exception("%s sync failed", tier)
        return {"status": "failed"}


async def run_light_sync() -> None:
    result = await _run_tier("light", "hourly")
    # Fire-and-forget: repair Devanagari titles that just got pulled in as
    # '?????' by the planner. Not awaited — the light sync already returned
    # so the scheduler is free.
    if result.get("status") not in ("skipped_concurrent", "failed"):
        try:
            from .repair_job import repair_mojibake_background
            asyncio.create_task(repair_mojibake_background())
        except Exception:
            log.exception("couldn't schedule mojibake repair")


async def run_medium_sync() -> None:
    await _run_tier("medium", "daily")


async def run_heavy_sync() -> None:
    # Heavy includes the weekly syllabus recheck — one job instead of two.
    await _run_tier("heavy", "weekly")
    try:
        from .syllabus_job import run_weekly_syllabus_check
        await run_weekly_syllabus_check()
    except Exception:
        log.exception("weekly syllabus check inside heavy sync failed")
    try:
        await _run_portal_resource_harvest()
    except Exception:
        log.exception("weekly resource harvest inside heavy sync failed")
    try:
        await _run_grade_match()
    except Exception:
        log.exception("weekly grade-assignment matcher inside heavy sync failed")
    try:
        await _run_topic_state_recompute()
    except Exception:
        log.exception("weekly topic-state recompute inside heavy sync failed")


async def _run_topic_state_recompute() -> None:
    """Rebuild every kid's topic_state from current grades + assignments.
    Idempotent. Drives the Phase 10 mastery-state model + Phase 11
    shaky-topics tray."""
    from ..db import get_async_session
    from ..services.topic_state import recompute_all
    log.info("weekly topic-state recompute: starting")
    async with get_async_session() as session:
        summary = await recompute_all(session)
    for c in summary["children"]:
        log.info("topic-state child=%s topics=%s states=%s",
                 c["child_id"], c["topics"], c["states"])


async def _run_grade_match() -> None:
    """Reconcile newly-graded items back to the assignments that produced
    them. Idempotent — strong existing links are kept; only weak/missing
    links are recomputed."""
    from ..db import get_async_session
    from ..services.grade_match import match_unlinked_grades
    log.info("weekly grade-match: starting")
    async with get_async_session() as session:
        summary = await match_unlinked_grades(session, use_llm_tiebreaker=True)
    log.info("weekly grade-match: %s", summary["counts"])


async def _run_portal_resource_harvest() -> None:
    """Refresh every portal-landing resource (spelling list, book lists,
    time tables, newsletters, syllabus PDFs, etc.) into data/rawdata/.
    Runs at heavy-tier cadence (weekly) — these items change rarely."""
    from sqlalchemy import select
    from ..db import get_async_session
    from ..models import Child
    from ..scraper.client import scraper_session
    from ..scraper import resources as R

    log.info("portal resource harvest: starting")
    async with get_async_session() as session:
        children = (await session.execute(select(Child))).scalars().all()
    async with scraper_session() as client:
        summary = await R.harvest_all(client, list(children))
    log.info(
        "portal resource harvest: saved=%d skipped=%d tiles=%d",
        len(summary["saved"]), len(summary["skipped"]), summary["tiles"],
    )


# Back-compat alias — keeps the old job id wiring if anything still refers
# to it. Scheduler will migrate to the new light/medium/heavy ids.
async def run_hourly_sync() -> None:
    await run_light_sync()
