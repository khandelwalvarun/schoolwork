"""Daily Mindspark metrics scrape — once per day, slow rate.

Slot 03:30 IST: well-spaced from the 02:00 brief warmup and 03:10
retention. Per-kid serial; errors logged but don't block other kids.
The scrape only runs if MINDSPARK_ENABLED=true AND the kid has
MINDSPARK_USERNAME_<id> + MINDSPARK_PASSWORD_<id> set.
"""
from __future__ import annotations

import logging

from ..config import get_settings
from ..scraper.mindspark.sync import run_metrics_all


log = logging.getLogger(__name__)


async def run_mindspark_daily() -> None:
    if not get_settings().mindspark_enabled:
        log.info("mindspark daily: disabled (MINDSPARK_ENABLED=false)")
        return
    log.info("mindspark daily: starting")
    try:
        out = await run_metrics_all()
    except Exception:
        log.exception("mindspark daily: failed")
        return
    log.info("mindspark daily: done — %s", out)
