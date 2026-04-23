"""Route events → channels per channel_config policy. Persists a Notification row
per (event, channel) whether fired, suppressed, or failed."""

from __future__ import annotations

import json
from datetime import datetime, time, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..channels.base import Channel, DeliveryResult
from ..channels.email import EmailChannel
from ..channels.inapp import InAppChannel
from ..channels.telegram import TelegramChannel
from ..models import ChannelConfig, Event, Notification

IST = ZoneInfo("Asia/Kolkata")

DEFAULT_CONFIG: dict[str, Any] = {
    "channels": {
        "telegram": {
            "enabled": True,
            "threshold": 0.6,
            "mute_kinds": [],
            "rate_limit": {"max_per_hour": 4, "quiet_hours_ist": "22:00-07:00"},
        },
        "email": {
            "enabled": True,
            "threshold": 0.8,
            "mute_kinds": [],
            "rate_limit": {"max_per_day": 6},
        },
        "inapp": {
            "enabled": True,
            "threshold": 0.0,
            "mute_kinds": [],
        },
        "digest": {
            "enabled": True,
            "delivery": ["telegram", "email", "inapp"],
        },
    }
}


def _parse_quiet_window(window: str | None) -> tuple[time, time] | None:
    if not window or "-" not in window:
        return None
    a, b = window.split("-", 1)
    try:
        h1, m1 = map(int, a.split(":"))
        h2, m2 = map(int, b.split(":"))
        return time(h1, m1), time(h2, m2)
    except Exception:
        return None


def _in_quiet_window(now_ist: datetime, window: tuple[time, time] | None) -> bool:
    if not window:
        return False
    start, end = window
    n = now_ist.time()
    if start <= end:
        return start <= n < end
    return n >= start or n < end


async def load_config(session: AsyncSession) -> dict[str, Any]:
    row = (
        await session.execute(select(ChannelConfig).where(ChannelConfig.id == 1))
    ).scalar_one_or_none()
    if row is None:
        return DEFAULT_CONFIG
    try:
        return json.loads(row.config_json)
    except Exception:
        return DEFAULT_CONFIG


async def save_config(session: AsyncSession, config: dict[str, Any]) -> None:
    existing = (
        await session.execute(select(ChannelConfig).where(ChannelConfig.id == 1))
    ).scalar_one_or_none()
    now = datetime.now(tz=timezone.utc)
    if existing:
        existing.config_json = json.dumps(config)
        existing.updated_at = now
    else:
        session.add(
            ChannelConfig(id=1, config_json=json.dumps(config), updated_at=now)
        )
    await session.commit()


def _build_channels() -> dict[str, Channel]:
    return {
        "telegram": TelegramChannel(),
        "email": EmailChannel(),
        "inapp": InAppChannel(),
    }


async def _rate_limit_ok(
    session: AsyncSession, channel: str, cfg: dict[str, Any], now: datetime
) -> bool:
    rl = cfg.get("rate_limit") or {}
    max_per_hour = rl.get("max_per_hour")
    max_per_day = rl.get("max_per_day")
    if max_per_hour:
        since = now - timedelta(hours=1)
        n = (
            await session.execute(
                select(func.count(Notification.id))
                .where(Notification.channel == channel)
                .where(Notification.status == "sent")
                .where(Notification.delivered_at >= since)
            )
        ).scalar_one()
        if n >= max_per_hour:
            return False
    if max_per_day:
        since = now - timedelta(days=1)
        n = (
            await session.execute(
                select(func.count(Notification.id))
                .where(Notification.channel == channel)
                .where(Notification.status == "sent")
                .where(Notification.delivered_at >= since)
            )
        ).scalar_one()
        if n >= max_per_day:
            return False
    return True


async def _already_delivered(
    session: AsyncSession, event_id: int, channel: str
) -> bool:
    row = (
        await session.execute(
            select(Notification.id)
            .where(Notification.event_id == event_id)
            .where(Notification.channel == channel)
            .where(Notification.status.in_(("sent", "suppressed")))
            .limit(1)
        )
    ).scalar_one_or_none()
    return row is not None


async def dispatch_event(
    session: AsyncSession, event_id: int
) -> list[DeliveryResult]:
    ev = (await session.execute(select(Event).where(Event.id == event_id))).scalar_one()
    ev_dict: dict[str, Any] = {
        "id": ev.id,
        "kind": ev.kind,
        "child_id": ev.child_id,
        "subject": ev.subject,
        "payload": json.loads(ev.payload_json) if ev.payload_json else {},
        "notability": ev.notability,
        "dedup_key": ev.dedup_key,
    }

    cfg = await load_config(session)
    channels_cfg = cfg.get("channels", {})
    channels = _build_channels()
    now = datetime.now(tz=timezone.utc)
    now_ist = now.astimezone(IST)

    results: list[DeliveryResult] = []

    for cname, ch in channels.items():
        pcfg = channels_cfg.get(cname, {})
        if await _already_delivered(session, event_id, cname):
            continue
        pending = Notification(
            event_id=event_id,
            channel=cname,
            status="pending",
            attempted_at=now,
        )
        session.add(pending)
        await session.flush()

        if not pcfg.get("enabled", True):
            pending.status = "suppressed"
            pending.error = "channel disabled"
            results.append(DeliveryResult(cname, "suppressed", "disabled"))
            continue
        if ev.notability < pcfg.get("threshold", 0.0):
            pending.status = "suppressed"
            pending.error = f"below threshold {pcfg.get('threshold')}"
            results.append(DeliveryResult(cname, "suppressed", pending.error))
            continue
        if ev.kind in pcfg.get("mute_kinds", []):
            pending.status = "suppressed"
            pending.error = "kind muted"
            results.append(DeliveryResult(cname, "suppressed", "muted"))
            continue

        if cname == "telegram":
            window = _parse_quiet_window(
                (pcfg.get("rate_limit") or {}).get("quiet_hours_ist")
            )
            if _in_quiet_window(now_ist, window):
                pending.status = "suppressed"
                pending.error = "quiet hours"
                results.append(DeliveryResult(cname, "suppressed", "quiet-hours"))
                continue

        if not await _rate_limit_ok(session, cname, pcfg, now):
            pending.status = "suppressed"
            pending.error = "rate limit"
            results.append(DeliveryResult(cname, "suppressed", "rate-limit"))
            continue

        try:
            r = await ch.send_event(ev_dict)
        except Exception as e:
            r = DeliveryResult(cname, "failed", error=str(e))

        pending.status = r.status
        pending.error = r.error
        pending.message_preview = r.message_preview
        if r.status == "sent":
            pending.delivered_at = datetime.now(tz=timezone.utc)
        results.append(r)

    await session.commit()
    return results
