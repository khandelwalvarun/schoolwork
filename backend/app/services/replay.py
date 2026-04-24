"""Counterfactual replay — given past events, show what the CURRENT channel
config would have done with each one (send / suppress, and why).

Does not re-send anything. Pure decision-logic walk."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Event, Notification
from ..notability.dispatcher import (
    DEFAULT_CONFIG,
    _in_quiet_window,
    _parse_quiet_window,
    load_config,
)


async def _actual_statuses(
    session: AsyncSession, event_ids: list[int]
) -> dict[int, dict[str, str]]:
    if not event_ids:
        return {}
    rows = (
        await session.execute(
            select(Notification.event_id, Notification.channel, Notification.status)
            .where(Notification.event_id.in_(event_ids))
        )
    ).all()
    out: dict[int, dict[str, str]] = {}
    for eid, ch, st in rows:
        out.setdefault(eid, {})[ch] = st
    return out


def _decide(
    channel: str, pcfg: dict[str, Any], ev_notability: float, ev_kind: str, now_ist
) -> tuple[str, str | None]:
    """Return (status, reason) — 'sent' | 'suppressed' + reason. No rate-limit
    in replay (rate-limit depends on past send counts which we don't recompute)."""
    if not pcfg.get("enabled", True):
        return "suppressed", "channel disabled"
    if ev_notability < pcfg.get("threshold", 0.0):
        return "suppressed", f"below threshold {pcfg.get('threshold')}"
    if ev_kind in pcfg.get("mute_kinds", []):
        return "suppressed", "kind muted"
    if channel == "telegram":
        window = _parse_quiet_window((pcfg.get("rate_limit") or {}).get("quiet_hours_ist"))
        if _in_quiet_window(now_ist, window):
            return "suppressed", "quiet hours"
    return "sent", None


async def replay_notifications(
    session: AsyncSession,
    since_days: int = 7,
    child_id: int | None = None,
    limit: int = 200,
) -> dict[str, Any]:
    """Return per-event counterfactual verdicts under the current channel policy,
    alongside what actually happened."""
    since = datetime.now(tz=timezone.utc) - timedelta(days=since_days)
    q = select(Event).where(Event.created_at >= since)
    if child_id is not None:
        q = q.where(Event.child_id == child_id)
    q = q.order_by(desc(Event.created_at)).limit(limit)
    events = (await session.execute(q)).scalars().all()
    if not events:
        return {"events": [], "summary": {"would_send": 0, "would_suppress": 0, "changed": 0}}

    cfg = await load_config(session)
    channels_cfg = cfg.get("channels") or DEFAULT_CONFIG["channels"]
    actual = await _actual_statuses(session, [e.id for e in events])

    from ..util.time import now_ist as _now_ist
    now_ist = _now_ist()

    would_send = would_suppress = changed = 0
    out_events: list[dict[str, Any]] = []
    for e in events:
        per_channel: dict[str, dict[str, Any]] = {}
        for cname, pcfg in channels_cfg.items():
            if cname == "digest":
                continue
            status, reason = _decide(cname, pcfg, e.notability, e.kind, now_ist)
            act = (actual.get(e.id) or {}).get(cname)
            was_changed = act is not None and act != status
            if status == "sent":
                would_send += 1
            else:
                would_suppress += 1
            if was_changed:
                changed += 1
            per_channel[cname] = {
                "replay_status": status,
                "replay_reason": reason,
                "actual_status": act,
                "changed": was_changed,
            }
        out_events.append(
            {
                "event_id": e.id,
                "kind": e.kind,
                "child_id": e.child_id,
                "subject": e.subject,
                "notability": e.notability,
                "created_at": e.created_at.isoformat() if e.created_at else None,
                "channels": per_channel,
                "payload": json.loads(e.payload_json) if e.payload_json else {},
            }
        )

    return {
        "events": out_events,
        "summary": {
            "total": len(events),
            "would_send": would_send,
            "would_suppress": would_suppress,
            "changed": changed,
            "since_days": since_days,
        },
    }
