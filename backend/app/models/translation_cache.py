from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base


class TranslationCache(Base):
    """Content-addressed cache of LLM translations.

    Keyed on (sha256(source_text), target_lang). Every cache hit bumps
    `hits` and `last_used_at` so we can later identify cold rows for
    cleanup.
    """

    __tablename__ = "translation_cache"
    __table_args__ = (
        UniqueConstraint(
            "text_sha256", "target_lang", name="uq_translation_cache_key"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    text_sha256: Mapped[str] = mapped_column(String, nullable=False, index=True)
    target_lang: Mapped[str] = mapped_column(String, nullable=False)
    source_text: Mapped[str] = mapped_column(Text, nullable=False)
    translated_text: Mapped[str] = mapped_column(Text, nullable=False)
    model: Mapped[str | None] = mapped_column(String, nullable=True)
    hits: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    last_used_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
