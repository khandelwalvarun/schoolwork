from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db import Base


class VeracrossItem(Base):
    """Canonical row for anything scraped from Veracross.

    `kind` enumerates: assignment | grade | comment | attendance |
    message | report_card | schedule_item | school_message.
    """

    __tablename__ = "veracross_items"
    __table_args__ = (
        UniqueConstraint("child_id", "kind", "external_id", name="uq_vc_items_child_kind_extid"),
        Index("idx_vc_items_child_kind_date", "child_id", "kind", "due_or_date"),
        Index("idx_vc_items_status", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    child_id: Mapped[int] = mapped_column(ForeignKey("children.id"), nullable=False)
    kind: Mapped[str] = mapped_column(String, nullable=False)
    external_id: Mapped[str] = mapped_column(String, nullable=False)
    subject: Mapped[str | None] = mapped_column(String, nullable=True)
    title: Mapped[str | None] = mapped_column(String, nullable=True)
    due_or_date: Mapped[str | None] = mapped_column(String, nullable=True)
    raw_json: Mapped[str] = mapped_column(String, nullable=False)
    normalized_json: Mapped[str | None] = mapped_column(String, nullable=True)
    status: Mapped[str | None] = mapped_column(String, nullable=True)
    seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    parent_marked_submitted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    title_en: Mapped[str | None] = mapped_column(String, nullable=True)
    notes_en: Mapped[str | None] = mapped_column(String, nullable=True)
    # Phase 12.5 — the multi-paragraph description from the assignment-detail
    # popup (Veracross's "Notes" field). The parser was already extracting
    # this; we just weren't persisting it. Stays in original language —
    # `notes_en` carries the translated-to-English copy when needed.
    body: Mapped[str | None] = mapped_column(String, nullable=True)
    # Phase 17 — Zimmerman self-prediction loop. The kid taps a band before
    # the test ("high"/"mid"/"low" or numeric "%85"); after the grade lands,
    # services/self_prediction computes the outcome ("matched"/"better"/
    # "worse"). Together they drive the calibration sparkline on Detail.
    self_prediction: Mapped[str | None] = mapped_column(String, nullable=True)
    self_prediction_set_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    self_prediction_outcome: Mapped[str | None] = mapped_column(
        String, nullable=True,
    )
    # Phase 22 — cached 1-sentence summary (school-message dedup view).
    # Generated on-demand via local Ollama and shared across every row
    # in the same dedup group so we don't re-call the LLM per click.
    llm_summary: Mapped[str | None] = mapped_column(String, nullable=True)
    llm_summary_url: Mapped[str | None] = mapped_column(String, nullable=True)
    # Professional status tracking (migration 0006)
    parent_status: Mapped[str | None] = mapped_column(String, nullable=True)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    snooze_until: Mapped[str | None] = mapped_column(String, nullable=True)
    status_notes: Mapped[str | None] = mapped_column(String, nullable=True)
    tags_json: Mapped[str | None] = mapped_column(String, nullable=True)
    detail_fetched_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # Grade ↔ assignment matching (migration 0009)
    linked_assignment_id: Mapped[int | None] = mapped_column(
        Integer, nullable=True, index=True,
    )
    match_confidence: Mapped[float | None] = mapped_column(nullable=True)
    match_method: Mapped[str | None] = mapped_column(String, nullable=True)
    # Phase 23 — "worth a chat" flag for the next parent-teacher
    # meeting. Timestamp doubles as the on/off bit (NULL = not flagged).
    # The optional note carries the parent's one-line reason so the
    # PTM brief can render it as a talking point verbatim.
    discuss_with_teacher_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    discuss_with_teacher_note: Mapped[str | None] = mapped_column(
        String, nullable=True,
    )
    # Phase 26 — three-bucket schoolwork category collapsed from
    # Veracross's verbose `type` field. {classwork, homework, review}.
    # Classwork hides from overdue/due_today/upcoming buckets;
    # review drives the prep workflow without title-regex guessing.
    # Classified at sync-time by services/work_category.py.
    work_category: Mapped[str | None] = mapped_column(String, nullable=True)

    # Phase 28 — anomaly auto-explainer. Detection (services/anomaly.py)
    # is purely deterministic; this column lets the parent acknowledge
    # the flag once they've seen it so the Today banner doesn't keep
    # re-surfacing historic anomalies forever.
    # Values: None (never flagged), 'open' (flagged, awaiting review),
    # 'dismissed' (parent saw it and is fine), 'escalated' (parent
    # marked it Worth-a-Chat or noted concern), 'reviewed' (looked at,
    # no action needed but keep in record).
    anomaly_status: Mapped[str | None] = mapped_column(String, nullable=True)
    anomaly_status_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )

    child = relationship("Child", back_populates="items")
