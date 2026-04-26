from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db import Base


class Notification(Base):
    __tablename__ = "notifications"
    __table_args__ = (
        Index("idx_notif_event", "event_id"),
        Index("idx_notif_status", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id"), nullable=False)
    channel: Mapped[str] = mapped_column(String, nullable=False)  # telegram|email|inapp|digest|mcp
    status: Mapped[str] = mapped_column(String, nullable=False)  # pending|sent|failed|suppressed
    attempted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error: Mapped[str | None] = mapped_column(String, nullable=True)
    message_preview: Mapped[str | None] = mapped_column(String, nullable=True)
    # Phase 14 — three-tier delivery + (why?) explainability + snooze.
    tier: Mapped[str | None] = mapped_column(String, nullable=True)  # now|today|weekly
    rule_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    why_json: Mapped[str | None] = mapped_column(String, nullable=True)

    event = relationship("Event", back_populates="notifications")
