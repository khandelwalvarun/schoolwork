"""SMTP email channel. Plain HTML email; no fancy templating yet."""

from __future__ import annotations

import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any

from ..config import get_settings
from .base import Channel, DeliveryResult


class EmailChannel(Channel):
    name = "email"

    def __init__(self) -> None:
        s = get_settings()
        self.host = s.smtp_host
        self.port = s.smtp_port
        self.user = s.smtp_user
        self.password = s.smtp_password
        self.from_addr = s.smtp_from
        self.to_addrs = [x.strip() for x in s.email_to.split(",") if x.strip()]

    def _enabled(self) -> bool:
        return bool(self.host and self.from_addr and self.to_addrs)

    def _send_sync(self, subject: str, html: str, text: str) -> DeliveryResult:
        if not self._enabled():
            return DeliveryResult(
                channel=self.name, status="suppressed",
                error="email disabled (no SMTP or recipients)",
                message_preview=text[:200],
            )
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = self.from_addr
        msg["To"] = ", ".join(self.to_addrs)
        msg.attach(MIMEText(text, "plain", "utf-8"))
        msg.attach(MIMEText(html, "html", "utf-8"))
        try:
            with smtplib.SMTP(self.host, self.port, timeout=20) as server:
                server.starttls()
                if self.user:
                    server.login(self.user, self.password)
                server.sendmail(self.from_addr, self.to_addrs, msg.as_string())
            return DeliveryResult(channel=self.name, status="sent", message_preview=text[:200])
        except Exception as e:
            return DeliveryResult(
                channel=self.name, status="failed",
                error=str(e), message_preview=text[:200],
            )

    async def send_event(self, event: dict[str, Any]) -> DeliveryResult:
        import asyncio
        text = self.render_event_text(event)
        subject = f"Parent Cockpit — {event['kind']}"
        html = f"<pre style='font-family:ui-sans-serif'>{text}</pre>"
        return await asyncio.to_thread(self._send_sync, subject, html, text)

    async def send_digest(self, rendered: dict[str, Any]) -> DeliveryResult:
        import asyncio
        text = rendered.get("text") or rendered.get("markdown") or ""
        html = rendered.get("html") or f"<pre>{text}</pre>"
        subject = rendered.get("subject", "Parent Cockpit — Daily Digest")
        return await asyncio.to_thread(self._send_sync, subject, html, text)

    async def send_test(self, message: str) -> DeliveryResult:
        import asyncio
        return await asyncio.to_thread(
            self._send_sync, "Parent Cockpit — test", f"<p>{message}</p>", message
        )
