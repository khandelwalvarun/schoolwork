"""Channel ABC. Each channel decides how to render and deliver an Event (or a digest)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass
class DeliveryResult:
    channel: str
    status: str  # "sent" | "failed" | "suppressed"
    error: str | None = None
    message_preview: str | None = None


class Channel(ABC):
    name: str

    @abstractmethod
    async def send_event(self, event: dict[str, Any]) -> DeliveryResult: ...

    @abstractmethod
    async def send_digest(self, rendered: dict[str, Any]) -> DeliveryResult: ...

    @abstractmethod
    async def send_test(self, message: str) -> DeliveryResult: ...

    def render_event_text(self, event: dict[str, Any]) -> str:
        """Default plain-text rendering for a notability event."""
        kind = event["kind"]
        payload = event.get("payload", {}) or {}
        subject = event.get("subject") or payload.get("subject") or ""
        title = payload.get("title") or payload.get("external_id") or ""
        days = payload.get("days_overdue")
        header = {
            "overdue_3d": "🚨 Overdue 3d",
            "overdue_7d": "🚨 Overdue 7d",
            "school_message": "📬 School message",
            "new_assignment": "📌 New assignment",
            "backlog_accelerating": "📈 Backlog accelerating",
            "subject_concentration": "🧱 Subject concentration",
            "comment_long": "💬 Teacher comment",
            "report_card_posted": "🎓 Report card posted",
            "scraper_drift": "⚠ Scraper drift",
            "sync_failed": "❌ Sync failed",
        }.get(kind, kind)
        lines = [f"{header}"]
        if subject:
            lines.append(f"Subject: {subject}")
        if title:
            lines.append(f"{title}")
        if days:
            lines.append(f"(+{days}d overdue)")
        return "\n".join(lines)
