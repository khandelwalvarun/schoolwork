from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    DateTime, ForeignKey, Index, Integer, String, func,
)
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base


class LibraryFile(Base):
    """Parent-uploaded file in the library — textbook PDFs, scanned
    newsletters, study guides, anything they want indexed.

    The LLM-classified columns (`llm_*`) are filled in shortly after
    upload by services/library_classify.py: text is pulled from the
    file (PDF via pypdf; plain text read directly), and Claude returns
    a structured classification — kind, subject, class_level, a 2-3
    sentence summary, and keywords. If classification fails (LLM down,
    binary file, etc.) `llm_error` carries the reason and the row stays
    visible for manual triage.
    """

    __tablename__ = "library_files"
    __table_args__ = (
        Index("idx_library_files_child", "child_id"),
        Index("idx_library_files_kind", "llm_kind"),
        Index("idx_library_files_subject", "llm_subject"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    filename: Mapped[str] = mapped_column(String, nullable=False)
    original_filename: Mapped[str | None] = mapped_column(String, nullable=True)
    sha256: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    mime_type: Mapped[str | None] = mapped_column(String, nullable=True)
    local_path: Mapped[str] = mapped_column(String, nullable=False)
    child_id: Mapped[int | None] = mapped_column(
        ForeignKey("children.id"), nullable=True,
    )
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )
    note: Mapped[str | None] = mapped_column(String, nullable=True)
    llm_kind: Mapped[str | None] = mapped_column(String, nullable=True)
    llm_subject: Mapped[str | None] = mapped_column(String, nullable=True)
    llm_class_level: Mapped[int | None] = mapped_column(Integer, nullable=True)
    llm_summary: Mapped[str | None] = mapped_column(String, nullable=True)
    llm_keywords: Mapped[str | None] = mapped_column(String, nullable=True)
    llm_processed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    llm_model: Mapped[str | None] = mapped_column(String, nullable=True)
    llm_error: Mapped[str | None] = mapped_column(String, nullable=True)
