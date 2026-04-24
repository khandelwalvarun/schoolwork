"""Summarise the scraper's health for the Settings → Veracross page.

- healthy:                last sync ended with status='ok'
- needs_reauth:           most recent failure is of the `needs_reauth:` kind
- consecutive_failures:   count back from the latest run while status != ok
- last_success / last_failure / last_error
- storage_state_exists:   is the persisted session cookie file on disk
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import get_settings
from ..models import SyncRun


def classify_error(err: str | None) -> dict[str, str]:
    """Map a raw sync-error string onto one of a fixed set of causes with a
    human-friendly label and a suggested action. Adding new cases here is
    how we wire new remediation flows.

    Codes:
      needs_reauth         — Veracross session expired; CAPTCHA blocks auto-relogin
      auth_failure         — credentials wrong, or reCAPTCHA token rejected
      network_timeout      — goto/navigation timed out (portal slow or offline)
      playwright_missing   — scraper executable or browser not installed
      scraper_drift        — selector mismatch / parser returned 0 rows
      unknown              — everything else
    """
    e = (err or "").strip()
    low = e.lower()
    if not e:
        return {"code": "unknown", "label": "Unknown error", "hint": "", "suggested_action": "view_logs"}
    if "needs_reauth" in low:
        return {
            "code": "needs_reauth",
            "label": "Veracross session expired",
            "hint": "A human needs to solve the reCAPTCHA to sign in again.",
            "suggested_action": "remote_login",
        }
    if "login failed" in low:
        return {
            "code": "auth_failure",
            "label": "Login rejected",
            "hint": "Username / password may be wrong, or reCAPTCHA didn't clear.",
            "suggested_action": "remote_login",
        }
    if "timeout" in low and ("goto" in low or "navigation" in low or "page." in low):
        return {
            "code": "network_timeout",
            "label": "Portal timed out",
            "hint": "Veracross may be slow right now. Retry in a minute.",
            "suggested_action": "retry",
        }
    if "executable doesn't exist" in low or "playwright install" in low or "browsertype.launch" in low:
        return {
            "code": "playwright_missing",
            "label": "Browser not installed",
            "hint": "Run `uv run playwright install chromium` on the server.",
            "suggested_action": "install_browser",
        }
    if "no such element" in low or "selector" in low or "parser" in low:
        return {
            "code": "scraper_drift",
            "label": "Page layout changed",
            "hint": "Veracross updated the DOM; scraper selectors need a fix.",
            "suggested_action": "view_logs",
        }
    return {"code": "unknown", "label": "Sync failed", "hint": e[:160], "suggested_action": "view_logs"}


async def snapshot(session: AsyncSession, limit: int = 20) -> dict[str, Any]:
    runs = (
        await session.execute(
            select(SyncRun).order_by(desc(SyncRun.started_at)).limit(limit)
        )
    ).scalars().all()

    last_success = next((r for r in runs if (r.status or "") == "ok"), None)
    last_failure = next((r for r in runs if (r.status or "") not in ("ok", "running")), None)
    latest = runs[0] if runs else None

    consecutive_failures = 0
    for r in runs:
        st = r.status or ""
        if st == "running":
            continue
        if st != "ok":
            consecutive_failures += 1
        else:
            break

    cause = classify_error(last_failure.error if last_failure else None) if last_failure else {
        "code": "ok", "label": "OK", "hint": "", "suggested_action": None,
    }

    s = get_settings()
    storage_state_exists = Path(s.scraper_storage_state_path).exists()

    latest_status = (latest.status if latest else None) or "never"
    healthy = latest_status == "ok"
    currently_running = latest_status == "running"

    return {
        "healthy": healthy,
        "currently_running": currently_running,
        "latest_status": latest_status,
        "needs_reauth": cause["code"] in ("needs_reauth", "auth_failure") and not healthy,
        "consecutive_failures": consecutive_failures,
        "last_success_at": last_success.ended_at.isoformat() if last_success and last_success.ended_at else None,
        "last_failure_at": last_failure.ended_at.isoformat() if last_failure and last_failure.ended_at else None,
        "last_error": (last_failure.error if last_failure else None),
        "cause_code": cause["code"],
        "cause_label": cause["label"],
        "cause_hint": cause["hint"],
        "suggested_action": cause["suggested_action"],
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
