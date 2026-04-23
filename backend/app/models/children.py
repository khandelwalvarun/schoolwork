from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db import Base


class Child(Base):
    __tablename__ = "children"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    display_name: Mapped[str] = mapped_column(String, nullable=False)
    class_level: Mapped[int] = mapped_column(Integer, nullable=False)
    class_section: Mapped[str | None] = mapped_column(String, nullable=True)
    school: Mapped[str] = mapped_column(String, nullable=False, default="Vasant Valley")
    veracross_id: Mapped[str | None] = mapped_column(String, nullable=True, unique=True)
    syllabus_path: Mapped[str | None] = mapped_column(String, nullable=True)
    settings: Mapped[str] = mapped_column(String, nullable=False, default="{}")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    items = relationship("VeracrossItem", back_populates="child")
    events = relationship("Event", back_populates="child")
