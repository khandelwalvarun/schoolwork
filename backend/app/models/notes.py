from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base


class ParentNote(Base):
    __tablename__ = "parent_notes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    child_id: Mapped[int | None] = mapped_column(ForeignKey("children.id"), nullable=True)
    note: Mapped[str] = mapped_column(String, nullable=False)
    tags: Mapped[str | None] = mapped_column(String, nullable=True)
    note_date: Mapped[date] = mapped_column(Date, server_default=func.current_date(), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
