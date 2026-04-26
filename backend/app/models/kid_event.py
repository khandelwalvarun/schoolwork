from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    DateTime, ForeignKey, Index, Integer, String, func,
)
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base


class KidEvent(Base):
    """A kid-relevant calendar event the parent wants on the radar.

    Source can be `manual` (typed in by the parent), `school_message`
    (auto-extracted by the LLM from a school_message row), or future
    integrations like `google_cal`. The cockpit treats them
    uniformly — what matters at display time is `start_date`,
    `event_type`, and `importance`.
    """

    __tablename__ = "kid_events"
    __table_args__ = (
        Index("idx_kid_events_start", "start_date"),
        Index("idx_kid_events_child", "child_id"),
        Index("idx_kid_events_source", "source"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    child_id: Mapped[int | None] = mapped_column(
        ForeignKey("children.id"), nullable=True,
    )
    title: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str | None] = mapped_column(String, nullable=True)
    event_type: Mapped[str | None] = mapped_column(String, nullable=True)
    importance: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    start_date: Mapped[str] = mapped_column(String, nullable=False)
    end_date: Mapped[str | None] = mapped_column(String, nullable=True)
    start_time: Mapped[str | None] = mapped_column(String, nullable=True)
    location: Mapped[str | None] = mapped_column(String, nullable=True)
    source: Mapped[str] = mapped_column(String, nullable=False, default="manual")
    source_ref: Mapped[str | None] = mapped_column(String, nullable=True)
    notes: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )
