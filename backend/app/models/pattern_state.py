from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean, DateTime, ForeignKey, Index, Integer, JSON, String,
    UniqueConstraint, func,
)
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base


class PatternState(Base):
    """One row per (child × calendar month) — three boolean behaviour
    flags + a JSON `detail` payload of supporting evidence.

    Computed by services/patterns.py from VeracrossItem rows + their
    grade-link history. *Never* drives notifications — surfaced only as
    a quiet card on the per-kid Detail page.
    """

    __tablename__ = "pattern_state"
    __table_args__ = (
        UniqueConstraint("child_id", "month", name="uq_pattern_state_child_month"),
        Index("idx_pattern_state_child", "child_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    child_id: Mapped[int] = mapped_column(ForeignKey("children.id"), nullable=False)
    month: Mapped[str] = mapped_column(String, nullable=False)  # "YYYY-MM"
    lateness: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    repeated_attempt: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    weekend_cramming: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    detail: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )
