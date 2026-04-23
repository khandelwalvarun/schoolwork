"""In-app channel. Nothing to 'send' externally — UI reads `/api/notifications`.
We just record that the event is available in-app."""

from __future__ import annotations

from typing import Any

from .base import Channel, DeliveryResult


class InAppChannel(Channel):
    name = "inapp"

    async def send_event(self, event: dict[str, Any]) -> DeliveryResult:
        return DeliveryResult(
            channel=self.name, status="sent",
            message_preview=self.render_event_text(event)[:200],
        )

    async def send_digest(self, rendered: dict[str, Any]) -> DeliveryResult:
        return DeliveryResult(
            channel=self.name, status="sent",
            message_preview=(rendered.get("text") or "")[:200],
        )

    async def send_test(self, message: str) -> DeliveryResult:
        return DeliveryResult(channel=self.name, status="sent", message_preview=message[:200])
