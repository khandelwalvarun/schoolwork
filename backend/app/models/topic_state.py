from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    DateTime, Float, ForeignKey, Integer, String, UniqueConstraint, func, Index,
)
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base


class TopicState(Base):
    """Per-(child × class × subject × topic) mastery row.

    Computed by services/topic_state.py from grades + assignments
    tagged to the syllabus topic. Khan-style heuristics + Cepeda decay.
    """

    __tablename__ = "topic_state"
    __table_args__ = (
        UniqueConstraint("child_id", "class_level", "subject", "topic", name="uq_topic_state"),
        Index("idx_topic_state_child", "child_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    child_id: Mapped[int] = mapped_column(ForeignKey("children.id"), nullable=False)
    class_level: Mapped[int] = mapped_column(Integer, nullable=False)
    subject: Mapped[str] = mapped_column(String, nullable=False)
    topic: Mapped[str] = mapped_column(String, nullable=False)
    state: Mapped[str] = mapped_column(String, nullable=False)
    last_assessed_at: Mapped[str | None] = mapped_column(String, nullable=True)
    last_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    proficient_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )
