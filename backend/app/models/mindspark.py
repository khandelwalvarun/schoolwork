from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    DateTime, Float, ForeignKey, Index, Integer, String,
    UniqueConstraint, func,
)
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base


class MindsparkSession(Base):
    """One row per Mindspark practice session for a kid.

    Aggregate metrics ONLY — never the question content. See migration
    0020 docstring for the scope contract.
    """

    __tablename__ = "mindspark_session"
    __table_args__ = (
        UniqueConstraint("child_id", "external_id", name="uq_ms_session_child_extid"),
        Index("idx_ms_session_child", "child_id"),
        Index("idx_ms_session_started", "started_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    child_id: Mapped[int] = mapped_column(ForeignKey("children.id"), nullable=False)
    external_id: Mapped[str] = mapped_column(String, nullable=False)
    subject: Mapped[str | None] = mapped_column(String, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    ended_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    duration_sec: Mapped[int | None] = mapped_column(Integer, nullable=True)
    questions_total: Mapped[int | None] = mapped_column(Integer, nullable=True)
    questions_correct: Mapped[int | None] = mapped_column(Integer, nullable=True)
    accuracy_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    topic_name: Mapped[str | None] = mapped_column(String, nullable=True)
    raw_json: Mapped[str | None] = mapped_column(String, nullable=True)
    seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )


class MindsparkTopicProgress(Base):
    """Per-(kid × subject × topic) snapshot from Mindspark's topic map.
    Updated in-place on each sync (replace, not append). See migration
    0020 docstring for scope contract."""

    __tablename__ = "mindspark_topic_progress"
    __table_args__ = (
        UniqueConstraint(
            "child_id", "subject", "topic_name",
            name="uq_ms_topic_child_subj_name",
        ),
        Index("idx_ms_topic_child", "child_id"),
        Index("idx_ms_topic_subject", "subject"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    child_id: Mapped[int] = mapped_column(ForeignKey("children.id"), nullable=False)
    subject: Mapped[str] = mapped_column(String, nullable=False)
    topic_id: Mapped[str | None] = mapped_column(String, nullable=True)
    topic_name: Mapped[str] = mapped_column(String, nullable=False)
    accuracy_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    questions_attempted: Mapped[int | None] = mapped_column(Integer, nullable=True)
    time_spent_sec: Mapped[int | None] = mapped_column(Integer, nullable=True)
    mastery_level: Mapped[str | None] = mapped_column(String, nullable=True)
    last_activity_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    raw_json: Mapped[str | None] = mapped_column(String, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )
