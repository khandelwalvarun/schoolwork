"""SQLAlchemy model for persisted LLM analyses.
Schema: migration 0026."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base


class LLMAnalysis(Base):
    __tablename__ = "llm_analysis"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    child_id: Mapped[int | None] = mapped_column(
        ForeignKey("children.id", ondelete="SET NULL"), nullable=True,
    )
    query: Mapped[str] = mapped_column(String, nullable=False)
    scope_days: Mapped[int] = mapped_column(
        Integer, nullable=False, default=30, server_default="30",
    )
    output_md: Mapped[str | None] = mapped_column(String, nullable=True)
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
