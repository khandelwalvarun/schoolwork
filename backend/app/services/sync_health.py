"""Summarise the scraper's health for the Settings → Veracross page.

- healthy:                last sync ended with status='ok'
- needs_reauth:           most recent failure is of the `needs_reauth:` kind
- consecutive_failures:   count back from the latest run while status != ok
- last_success / last_failure / last_error
- storage_state_exists:   is `recon/storage_state.json` on disk
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import get_settings
from ..models import SyncRun


async def snapshot(session: AsyncSession, limit: int = 20) -> dict[str, Any]:
    runs = (
        await session.execute(
            select(SyncRun).order_by(desc(SyncRun.started_at)).limit(limit)
        )
    ).scalars().all()

    last_success = next((r for r in runs if (r.status or "") == "ok"), None)
    last_failure = next((r for r in runs if (r.status or "") != "ok"), None)

    consecutive_failures = 0
    for r in runs:
        if (r.status or "") != "ok":
            consecutive_failures += 1
        else:
            break

    needs_reauth = False
    if last_failure and last_failure.error and "needs_reauth" in last_failure.error:
        needs_reauth = True

    s = get_settings()
    storage_state_exists = Path(s.scraper_storage_state_path).exists()

    return {
        "healthy": bool(runs) and (runs[0].status or "") == "ok",
        "needs_reauth": needs_reauth,
        "consecutive_failures": consecutive_failures,
        "last_success_at": last_success.ended_at.isoformat() if last_success and last_success.ended_at else None,
        "last_failure_at": last_failure.ended_at.isoformat() if last_failure and last_failure.ended_at else None,
        "last_error": (last_failure.error if last_failure else None),
        "storage_state_exists": storage_state_exists,
        "recent_runs": [
            {
                "id": r.id,
                "status": r.status,
                "started_at": r.started_at.isoformat() if r.started_at else None,
                "ended_at": r.ended_at.isoformat() if r.ended_at else None,
                "duration_sec": (
                    (r.ended_at - r.started_at).total_seconds()
                    if r.ended_at and r.started_at else None
                ),
                "items_new": r.items_new,
                "items_updated": r.items_updated,
                "events_produced": r.events_produced,
                "error": (r.error or "")[:160],
            }
            for r in runs[:10]
        ],
    }
