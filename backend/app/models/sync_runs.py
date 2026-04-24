from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base


class SyncRun(Base):
    __tablename__ = "sync_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    trigger: Mapped[str] = mapped_column(String, nullable=False)  # hourly|manual|startup
    status: Mapped[str] = mapped_column(String, nullable=False)
    items_new: Mapped[int] = mapped_column(Integer, default=0)
    items_updated: Mapped[int] = mapped_column(Integer, default=0)
    events_produced: Mapped[int] = mapped_column(Integer, default=0)
    notifications_fired: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(String, nullable=True)
    warnings: Mapped[str | None] = mapped_column(String, nullable=True)
    log_text: Mapped[str | None] = mapped_column(String, nullable=True)
