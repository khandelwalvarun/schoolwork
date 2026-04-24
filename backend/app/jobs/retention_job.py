"""Retention: drop sync_run rows (and their logs) older than the policy
window. Default: 7 days. Runs daily at 03:10 IST via APScheduler.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, update, func

from ..db import get_async_session
from ..models import SyncRun

log = logging.getLogger(__name__)

RETENTION_DAYS = 7
MAX_LOG_BYTES = 200_000


async def prune_sync_logs(days: int = RETENTION_DAYS) -> dict[str, int | str]:
    cutoff = datetime.now(tz=timezone.utc) - timedelta(days=days)
    async with get_async_session() as session:
        deleted_result = await session.execute(
            delete(SyncRun).where(SyncRun.started_at < cutoff)
        )
        # Safety net: null any log_text larger than the cap (shouldn't happen
        # because run_sync already truncates, but guards the DB if an old row
        # slipped through).
        await session.execute(
            update(SyncRun)
            .where(func.length(SyncRun.log_text) > MAX_LOG_BYTES)
            .values(log_text=None)
        )
        await session.commit()
        deleted = deleted_result.rowcount or 0
        log.info(
            "sync-log retention: deleted %d rows older than %d days (cutoff %s)",
            deleted, days, cutoff.isoformat(),
        )
        return {"deleted": int(deleted), "cutoff": cutoff.isoformat()}


async def run_daily_retention() -> None:
    await prune_sync_logs()
