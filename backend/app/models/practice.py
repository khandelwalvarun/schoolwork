"""SQLAlchemy models for practice-prep sessions, iterations, and
classwork scans. Schema definitions live in migration 0022."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db import Base


class PracticeSession(Base):
    """A persistent prep workspace. Each session is one upcoming
    review/test (or a free-form study session). Iterations accumulate
    inside it as the parent steers the LLM."""

    __tablename__ = "practice_session"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    child_id: Mapped[int] = mapped_column(ForeignKey("children.id"), nullable=False)
    subject: Mapped[str] = mapped_column(String, nullable=False)
    topic: Mapped[str | None] = mapped_column(String, nullable=True)
    linked_assignment_id: Mapped[int | None] = mapped_column(
        ForeignKey("veracross_items.id", ondelete="SET NULL"), nullable=True,
    )
    title: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, default="active")
    preferred_iteration_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )
    archived_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )

    iterations: Mapped[list["PracticeIteration"]] = relationship(
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="PracticeIteration.iteration_index",
    )
    scans: Mapped[list["PracticeClassworkScan"]] = relationship(
        back_populates="session",
        cascade="save-update, merge",  # scans can outlive a session
    )


class PracticeIteration(Base):
    """One generated draft within a practice session."""

    __tablename__ = "practice_iteration"
    __table_args__ = (
        UniqueConstraint(
            "session_id", "iteration_index",
            name="uq_practice_iteration_session_idx",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[int] = mapped_column(
        ForeignKey("practice_session.id", ondelete="CASCADE"), nullable=False,
    )
    iteration_index: Mapped[int] = mapped_column(Integer, nullable=False)
    parent_prompt: Mapped[str | None] = mapped_column(String, nullable=True)
    output_md: Mapped[str] = mapped_column(String, nullable=False)
    output_json: Mapped[str | None] = mapped_column(String, nullable=True)
    llm_used: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    llm_model: Mapped[str | None] = mapped_column(String, nullable=True)
    llm_input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    llm_output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )

    session: Mapped[PracticeSession] = relationship(back_populates="iterations")


class PracticeClassworkScan(Base):
    """A scan of recent classwork the parent uploaded to ground the LLM.

    The actual file lives in `attachments` (source_kind=practice_classwork);
    this row caches the Vision/OCR extraction so we don't re-call Claude
    on every iteration."""

    __tablename__ = "practice_classwork_scan"
    __table_args__ = (
        UniqueConstraint("attachment_id", name="uq_practice_scan_attachment"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[int | None] = mapped_column(
        ForeignKey("practice_session.id", ondelete="SET NULL"), nullable=True,
    )
    child_id: Mapped[int] = mapped_column(ForeignKey("children.id"), nullable=False)
    subject: Mapped[str] = mapped_column(String, nullable=False)
    attachment_id: Mapped[int] = mapped_column(
        ForeignKey("attachments.id", ondelete="CASCADE"), nullable=False,
    )
    extracted_text: Mapped[str | None] = mapped_column(String, nullable=True)
    extracted_summary: Mapped[str | None] = mapped_column(String, nullable=True)
    extracted_topics_json: Mapped[str | None] = mapped_column(String, nullable=True)
    extracted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )

    session: Mapped[PracticeSession | None] = relationship(back_populates="scans")
