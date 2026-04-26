"""Mindspark metrics scrape — every 3rd day at a randomized time
between 17:00 and 18:00 IST.

The scheduler fires the wrapper at 17:00 with `jitter=3600` so the
actual execution time falls uniformly in [17:00, 18:00) IST. Inside
the wrapper we check a persistent "last fired" file to enforce the
"every 3rd day" cadence — if the last successful run was < 3 days
ago we skip cleanly.

Why daytime instead of nightly: the laptop running this might be
asleep/off at 03:30. 17:00-18:00 is when the kid's done with school
and the parent is likely active, so the machine is awake. Slow-rate
is preserved (≥15-30s between page nav inside the scraper).

Why every 3rd day: scope per user request — Mindspark is reviewed
weekly-ish, not as a daily-monitor surface. Running 3× as often as
needed wastes Ei's bandwidth and our quota.

The scrape only runs if MINDSPARK_ENABLED=true AND at least one kid
has MINDSPARK_USERNAME_<id> + MINDSPARK_PASSWORD_<id> set.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

from ..config import REPO_ROOT, get_settings
from ..scraper.mindspark.sync import run_metrics_all


log = logging.getLogger(__name__)

# Cadence guard. Persistent across restarts so an unexpected reboot
# doesn't accidentally double-fire on the same day.
_LAST_FIRED_PATH = REPO_ROOT / "data" / "mindspark_state" / "last_fired.txt"
_CADENCE_DAYS = 3


def _last_fired_at() -> datetime | None:
    try:
        if not _LAST_FIRED_PATH.exists():
            return None
        s = _LAST_FIRED_PATH.read_text(encoding="utf-8").strip()
        if not s:
            return None
        return datetime.fromisoformat(s)
    except Exception as e:
        log.warning("mindspark: couldn't read last_fired (%s); treating as never-fired", e)
        return None


def _record_fired_at(dt: datetime) -> None:
    try:
        _LAST_FIRED_PATH.parent.mkdir(parents=True, exist_ok=True)
        _LAST_FIRED_PATH.write_text(dt.isoformat(), encoding="utf-8")
    except Exception:
        log.exception("mindspark: couldn't write last_fired marker")


async def run_mindspark_daily() -> None:
    """Wrapper invoked by APScheduler. Enforces the every-3rd-day
    cadence; fires the actual scrape only if enough time has passed
    since the last successful run."""
    if not get_settings().mindspark_enabled:
        log.info("mindspark scrape: disabled (MINDSPARK_ENABLED=false)")
        return

    last = _last_fired_at()
    now = datetime.now(tz=timezone.utc)
    if last is not None:
        elapsed = now - last
        # Use cadence - 12h so a "fired late on day N, fires early on
        # day N+3" doesn't drift the schedule indefinitely.
        threshold = timedelta(days=_CADENCE_DAYS, hours=-12)
        if elapsed < threshold:
            log.info(
                "mindspark scrape: skipped — last fired %s ago (cadence is %sd)",
                elapsed, _CADENCE_DAYS,
            )
            return

    log.info("mindspark scrape: starting (last fired: %s)", last or "never")
    try:
        out = await run_metrics_all()
    except Exception:
        log.exception("mindspark scrape: failed")
        return
    _record_fired_at(now)
    log.info("mindspark scrape: done — %s", out)
