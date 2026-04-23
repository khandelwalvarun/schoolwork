"""Daily + weekly digest jobs."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from sqlalchemy import insert

from ..channels.email import EmailChannel
from ..channels.inapp import InAppChannel
from ..channels.telegram import TelegramChannel
from ..db import get_async_session
from ..models import Event, Notification
from ..notability.dispatcher import load_config
from ..notability.rubric import DIGEST_4PM, DIGEST_WEEKLY
from ..services.briefing import generate_and_store_digest
from ..services.render import render_for_digest

log = logging.getLogger(__name__)


async def _dispatch_digest(event_kind: str, rendered: dict, period_key: str) -> None:
    cfg = await load_config_async()
    delivery = (cfg.get("channels", {}).get("digest") or {}).get(
        "delivery", ["telegram", "email", "inapp"]
    )
    channel_objs = {
        "telegram": TelegramChannel(),
        "email": EmailChannel(),
        "inapp": InAppChannel(),
    }

    # Create a synthetic Event so the notifications table ties to a concrete event id.
    now = datetime.now(tz=timezone.utc)
    async with get_async_session() as session:
        ev = Event(
            kind=event_kind,
            notability=1.0,
            payload_json=json.dumps({"period": period_key}, ensure_ascii=False),
            dedup_key=f"{event_kind}:{period_key}",
        )
        session.add(ev)
        try:
            await session.commit()
            await session.refresh(ev)
        except Exception:
            await session.rollback()
            existing = await session.execute(
                Event.__table__.select().where(
                    Event.__table__.c.dedup_key == f"{event_kind}:{period_key}"
                )
            )
            row = existing.first()
            if row is None:
                raise
            ev_id = row[0]
        else:
            ev_id = ev.id

        for name in delivery:
            ch = channel_objs.get(name)
            if ch is None:
                continue
            pending = Notification(
                event_id=ev_id,
                channel=name,
                status="pending",
                attempted_at=now,
            )
            session.add(pending)
            await session.flush()
            try:
                r = await ch.send_digest(rendered)
            except Exception as e:
                pending.status = "failed"
                pending.error = str(e)
                continue
            pending.status = r.status
            pending.error = r.error
            pending.message_preview = r.message_preview
            if r.status == "sent":
                pending.delivered_at = datetime.now(tz=timezone.utc)
        await session.commit()


async def load_config_async() -> dict:
    async with get_async_session() as session:
        return await load_config(session)


async def run_daily_digest() -> None:
    log.info("running daily digest")
    try:
        data = await generate_and_store_digest(kind="digest_4pm", llm=True)
        rendered = render_for_digest(data)
        await _dispatch_digest("digest_4pm", rendered, data.generated_for)
        log.info("daily digest delivered for %s", data.generated_for)
    except Exception:
        log.exception("daily digest failed")


async def run_weekly_digest() -> None:
    log.info("running weekly digest")
    try:
        data = await generate_and_store_digest(kind="weekly", llm=True)
        rendered = render_for_digest(data)
        # Period key includes ISO week so it dedups per week.
        from datetime import date
        week_key = date.today().strftime("%G-W%V")
        await _dispatch_digest("digest_weekly", rendered, week_key)
        log.info("weekly digest delivered for %s", week_key)
    except Exception:
        log.exception("weekly digest failed")
