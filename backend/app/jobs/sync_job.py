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


# Back-compat alias — keeps the old job id wiring if anything still refers
# to it. Scheduler will migrate to the new light/medium/heavy ids.
async def run_hourly_sync() -> None:
    await run_light_sync()
