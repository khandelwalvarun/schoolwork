from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db import Base


class Event(Base):
    """Every event ever computed, even the ones that did not fire.

    Enables replay + retuning of the notability rubric.
    """

    __tablename__ = "events"
    __table_args__ = (Index("idx_events_child_time", "child_id", "created_at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    kind: Mapped[str] = mapped_column(String, nullable=False)
    child_id: Mapped[int | None] = mapped_column(ForeignKey("children.id"), nullable=True)
    subject: Mapped[str | None] = mapped_column(String, nullable=True)
    related_item_id: Mapped[int | None] = mapped_column(
        ForeignKey("veracross_items.id"), nullable=True
    )
    payload_json: Mapped[str] = mapped_column(String, nullable=False)
    notability: Mapped[float] = mapped_column(Float, nullable=False)
    dedup_key: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    child = relationship("Child", back_populates="events")
    notifications = relationship("Notification", back_populates="event")
