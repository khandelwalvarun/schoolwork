"""Telegram bot channel. Sends markdown via Telegram Bot HTTP API."""

from __future__ import annotations

from typing import Any

import httpx

from ..config import get_settings
from .base import Channel, DeliveryResult


class TelegramChannel(Channel):
    name = "telegram"

    def __init__(self) -> None:
        s = get_settings()
        self.token = s.telegram_bot_token
        self.chat_ids = [x.strip() for x in s.telegram_chat_ids.split(",") if x.strip()]

    def _enabled(self) -> bool:
        return bool(self.token and self.chat_ids)

    async def _send(self, text: str) -> DeliveryResult:
        if not self._enabled():
            return DeliveryResult(
                channel=self.name, status="suppressed",
                error="telegram disabled (no token or chat_id)",
                message_preview=text[:200],
            )
        errors: list[str] = []
        async with httpx.AsyncClient(timeout=15.0) as c:
            for chat_id in self.chat_ids:
                try:
                    r = await c.post(
                        f"https://api.telegram.org/bot{self.token}/sendMessage",
                        json={
                            "chat_id": chat_id,
                            "text": text,
                            "parse_mode": "Markdown",
                            "disable_web_page_preview": True,
                        },
                    )
                    r.raise_for_status()
                except Exception as e:
                    errors.append(f"{chat_id}: {e}")
        if errors:
            return DeliveryResult(
                channel=self.name, status="failed",
                error="; ".join(errors), message_preview=text[:200],
            )
        return DeliveryResult(
            channel=self.name, status="sent", message_preview=text[:200]
        )

    async def send_event(self, event: dict[str, Any]) -> DeliveryResult:
        return await self._send(self.render_event_text(event))

    async def send_digest(self, rendered: dict[str, Any]) -> DeliveryResult:
        text = rendered.get("telegram") or rendered.get("text") or rendered.get("markdown") or ""
        return await self._send(text[:4000])  # telegram message cap 4096

    async def send_test(self, message: str) -> DeliveryResult:
        return await self._send(f"✅ Parent Cockpit test\n{message}")
