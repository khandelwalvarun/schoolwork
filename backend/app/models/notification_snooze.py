from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    DateTime, ForeignKey, Index, Integer, String, UniqueConstraint, func,
)
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base


class NotificationSnooze(Base):
    """Parent-set snooze on a (rule_id, child_id) pair until a moment.

    The dispatcher consults this table at fire time and suppresses with
    reason "snoozed by parent" when a row is active. `child_id` may be
    None for kid-agnostic rules (e.g. SYNC_FAILED).

    Snoozes are short-lived by design — the (why?) popover offers
    "1 day" / "1 week" options. After `until` passes, the row stays
    around as audit history (filtered out by the active query).
    """

    __tablename__ = "notification_snooze"
    __table_args__ = (
        UniqueConstraint("rule_id", "child_id", name="uq_notif_snooze_rule_child"),
        Index("idx_notif_snooze_rule", "rule_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    rule_id: Mapped[str] = mapped_column(String, nullable=False)
    child_id: Mapped[int | None] = mapped_column(
        ForeignKey("children.id"), nullable=True,
    )
    until: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    reason: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )
