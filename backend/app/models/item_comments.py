from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base


class ItemComment(Base):
    """Free-form parent (or future: kid / teacher-paraphrased) comment
    attached to one veracross_items row.

    Designed for LLM aggregation — denormalised `child_id` and `subject`
    let the comments feed into pack builders without a join, and
    optional `sentiment` / `topic` / `tags_json` give the LLM
    pre-faceted handles for clustering across many comments.

    Many comments per item is the expected case: observations
    accumulate as the parent works with the kid over time, and the
    pattern-mining job can read the whole timeline.
    """

    __tablename__ = "item_comments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    item_id: Mapped[int] = mapped_column(
        ForeignKey("veracross_items.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    child_id: Mapped[int] = mapped_column(
        ForeignKey("children.id"), nullable=False
    )
    subject: Mapped[str | None] = mapped_column(String, nullable=True)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    # Parent's quick read on the comment. None = unstratified.
    sentiment: Mapped[str | None] = mapped_column(String, nullable=True)
    # Fine-grained topic the comment is about — useful for LLM
    # clustering. e.g. "fractions", "writing organization", "test
    # anxiety", "didn't read directions".
    topic: Mapped[str | None] = mapped_column(String, nullable=True)
    tags_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Author defaults to 'parent'. Reserved for future automated entries
    # (e.g. 'kid_paraphrase', 'teacher_paraphrase').
    author: Mapped[str] = mapped_column(
        String, nullable=False, default="parent", server_default="parent"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


# Allowed sentiment values. None is also valid (unrated).
SENTIMENTS = ("positive", "neutral", "concern")
