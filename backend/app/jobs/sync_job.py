"""Hourly sync job entry point."""

from __future__ import annotations

import logging

from ..scraper.sync import run_sync

log = logging.getLogger(__name__)


async def run_hourly_sync() -> None:
    try:
        result = await run_sync(trigger="hourly")
        log.info(
            "hourly sync done: new=%d updated=%d events=%d fired=%d",
            result.get("items_new", 0),
            result.get("items_updated", 0),
            result.get("events_produced", 0),
            result.get("notifications_fired", 0),
        )
    except Exception:
        log.exception("hourly sync failed")
