"""APScheduler in-process. Runs hourly sync (08:00–22:00 IST), daily digest at
16:00 IST, weekly digest Sunday 20:00 IST. Started/stopped via FastAPI lifespan.
"""

from __future__ import annotations

import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from ..config import get_settings
from ..services.ui_prefs import load_prefs
from .brief_warmup_job import run_brief_warmup
from .digest_job import run_daily_digest, run_weekly_digest
from .mindspark_job import run_mindspark_daily
from .retention_job import run_daily_retention
from .sync_job import run_light_sync, run_medium_sync, run_heavy_sync

log = logging.getLogger(__name__)
_scheduler: AsyncIOScheduler | None = None


def get_scheduler() -> AsyncIOScheduler:
    global _scheduler
    if _scheduler is None:
        tz = get_settings().tz
        _scheduler = AsyncIOScheduler(timezone=tz)
    return _scheduler


def _sync_cron_trigger() -> CronTrigger:
    """Build the light-tier CronTrigger from the user-configurable prefs."""
    prefs = load_prefs()
    interval_h = max(1, int(prefs.get("sync_interval_hours") or 1))
    start = max(0, min(23, int(prefs.get("sync_window_start_hour") or 8)))
    end = max(0, min(23, int(prefs.get("sync_window_end_hour") or 22)))
    if end < start:
        start, end = 8, 22
    hours = ",".join(str(h) for h in range(start, end + 1, interval_h))
    return CronTrigger(hour=hours, minute=5)


def reschedule_sync_job() -> None:
    """Re-register light_sync with the latest trigger from prefs."""
    s = get_scheduler()
    s.add_job(
        run_light_sync,
        _sync_cron_trigger(),
        id="light_sync",
        replace_existing=True,
        coalesce=True,
        max_instances=1,
        misfire_grace_time=60,
    )
    log.info("rescheduled light_sync with trigger: %s", s.get_job("light_sync").trigger)


def start_scheduler() -> AsyncIOScheduler:
    s = get_scheduler()
    if s.running:
        return s
    # Light sync — user-configurable interval and window (default: hourly 08–22 IST).
    # Planner + messages only. Devanagari repair runs as a background task after.
    s.add_job(
        run_light_sync,
        _sync_cron_trigger(),
        id="light_sync",
        replace_existing=True,
        coalesce=True,
        max_instances=1,
        misfire_grace_time=60,
    )
    # Medium sync — once daily at 06:00 IST. Pulls grades + runs attachment
    # repair pass for items with stale (>24h) detail_fetched_at.
    s.add_job(
        run_medium_sync,
        CronTrigger(hour=6, minute=0),
        id="medium_sync",
        replace_existing=True,
        coalesce=True,
        max_instances=1,
        misfire_grace_time=900,
    )
    # Heavy sync — weekly Sunday 07:30 IST. Rediscovers grading periods +
    # class roster, refreshes the cache, then runs the syllabus recheck.
    s.add_job(
        run_heavy_sync,
        CronTrigger(day_of_week="sun", hour=7, minute=30),
        id="heavy_sync",
        replace_existing=True,
        coalesce=True,
        max_instances=1,
        misfire_grace_time=3600,
    )
    # Daily digest at 16:00 IST
    s.add_job(
        run_daily_digest,
        CronTrigger(hour=16, minute=0),
        id="daily_digest",
        replace_existing=True,
        coalesce=True,
        max_instances=1,
        misfire_grace_time=300,
    )
    # Weekly digest Sunday 20:00 IST
    s.add_job(
        run_weekly_digest,
        CronTrigger(day_of_week="sun", hour=20, minute=0),
        id="weekly_digest",
        replace_existing=True,
        coalesce=True,
        max_instances=1,
        misfire_grace_time=600,
    )
    # Syllabus recheck is subsumed by run_heavy_sync() above (same cadence,
    # same moment, one browser launch instead of two). Remove any legacy
    # job with the old id so the scheduler doesn't double-fire.
    try:
        s.remove_job("weekly_syllabus_check")
    except Exception:
        pass
    # Nightly brief warmup at 02:00 IST. Pre-generates the Sunday and
    # PTM briefs for both kids and writes JSON + MD to
    # data/cached_briefs/ so the next morning's page load serves
    # instantly. Each brief takes ~30s of Claude time × 2 kids × 2
    # kinds → ~2 minutes total.
    s.add_job(
        run_brief_warmup,
        CronTrigger(hour=2, minute=0),
        id="brief_warmup",
        replace_existing=True,
        coalesce=True,
        max_instances=1,
        misfire_grace_time=3600,
    )
    # Mindspark daily metrics scrape — 03:30 IST. Only fires when
    # MINDSPARK_ENABLED=true AND a kid has credentials configured.
    # Slow-rate enforced inside the scraper (≥15-30s between page
    # loads). Per-kid serial.
    s.add_job(
        run_mindspark_daily,
        CronTrigger(hour=3, minute=30),
        id="mindspark_daily",
        replace_existing=True,
        coalesce=True,
        max_instances=1,
        misfire_grace_time=3600,
    )
    # Daily retention: drop sync_runs older than 7 days so log_text doesn't
    # accumulate forever.
    s.add_job(
        run_daily_retention,
        CronTrigger(hour=3, minute=10),
        id="daily_retention",
        replace_existing=True,
        coalesce=True,
        max_instances=1,
        misfire_grace_time=3600,
    )
    s.start()
    log.info("scheduler started; jobs: %s", [j.id for j in s.get_jobs()])
    return s


def stop_scheduler() -> None:
    s = get_scheduler()
    if s.running:
        s.shutdown(wait=False)
        log.info("scheduler stopped")
