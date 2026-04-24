"""APScheduler in-process. Runs hourly sync (08:00–22:00 IST), daily digest at
16:00 IST, weekly digest Sunday 20:00 IST. Started/stopped via FastAPI lifespan.
"""

from __future__ import annotations

import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from ..config import get_settings
from ..services.ui_prefs import load_prefs
from .digest_job import run_daily_digest, run_weekly_digest
from .sync_job import run_hourly_sync
from .syllabus_job import run_weekly_syllabus_check

log = logging.getLogger(__name__)
_scheduler: AsyncIOScheduler | None = None


def get_scheduler() -> AsyncIOScheduler:
    global _scheduler
    if _scheduler is None:
        tz = get_settings().tz
        _scheduler = AsyncIOScheduler(timezone=tz)
    return _scheduler


def _sync_cron_trigger() -> CronTrigger:
    """Build the sync CronTrigger from the user-configurable prefs."""
    prefs = load_prefs()
    interval_h = max(1, int(prefs.get("sync_interval_hours") or 1))
    start = max(0, min(23, int(prefs.get("sync_window_start_hour") or 8)))
    end = max(0, min(23, int(prefs.get("sync_window_end_hour") or 22)))
    if end < start:
        start, end = 8, 22
    hours = ",".join(str(h) for h in range(start, end + 1, interval_h))
    return CronTrigger(hour=hours, minute=5)


def reschedule_sync_job() -> None:
    """Re-register hourly_sync with the latest trigger from prefs. Safe to
    call anytime — APScheduler replaces the existing job by id."""
    s = get_scheduler()
    s.add_job(
        run_hourly_sync,
        _sync_cron_trigger(),
        id="hourly_sync",
        replace_existing=True,
        coalesce=True,
        max_instances=1,
        misfire_grace_time=60,
    )
    log.info("rescheduled hourly_sync with trigger: %s", s.get_job("hourly_sync").trigger)


def start_scheduler() -> AsyncIOScheduler:
    s = get_scheduler()
    if s.running:
        return s
    # Sync — user-configurable interval and window (default: hourly 08–22 IST)
    s.add_job(
        run_hourly_sync,
        _sync_cron_trigger(),
        id="hourly_sync",
        replace_existing=True,
        coalesce=True,
        max_instances=1,
        misfire_grace_time=60,
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
    # Weekly syllabus recheck — Sunday 07:30 IST (early, before Monday
    # assignments get set against the new week's cycle).
    s.add_job(
        run_weekly_syllabus_check,
        CronTrigger(day_of_week="sun", hour=7, minute=30),
        id="weekly_syllabus_check",
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
