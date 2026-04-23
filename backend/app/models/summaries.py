from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base


class Summary(Base):
    __tablename__ = "summaries"
    __table_args__ = (UniqueConstraint("child_id", "kind", "period_start", name="uq_summaries_child_kind_period"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    child_id: Mapped[int | None] = mapped_column(ForeignKey("children.id"), nullable=True)
    kind: Mapped[str] = mapped_column(String, nullable=False)  # digest_4pm | weekly | cycle_review
    period_start: Mapped[str] = mapped_column(String, nullable=False)
    period_end: Mapped[str] = mapped_column(String, nullable=False)
    content_md: Mapped[str] = mapped_column(String, nullable=False)
    stats_json: Mapped[str] = mapped_column(String, nullable=False)
    model_used: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
