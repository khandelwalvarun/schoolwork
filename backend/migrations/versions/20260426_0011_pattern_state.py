"""Add pattern_state table — monthly behavioural patterns per kid.

Three boolean flags: lateness, repeated_attempt, weekend_cramming. The
detail blob carries supporting evidence (counts, example items) so the
UI can show "why this triggered" without re-running the math.

Quiet output by design — these never push notifications. They show up
on the per-kid Detail page as a passive card.

  child_id × month — uniquely keyed (one row per month per kid)
  lateness            — assignments graded > 3 d after due, ≥ 3 in month
  repeated_attempt    — same topic graded ≥ 3 times in month
  weekend_cramming    — ≥ 60 % of activity-bearing days fall Sat/Sun
  detail              — JSON blob: per-flag counts + sample item titles

Revision ID: 0011
Revises: 0010
Create Date: 2026-04-26
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "pattern_state",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("child_id", sa.Integer(), sa.ForeignKey("children.id"), nullable=False),
        sa.Column("month", sa.String(), nullable=False),  # "YYYY-MM"
        sa.Column("lateness", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("repeated_attempt", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("weekend_cramming", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("detail", sa.JSON(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("child_id", "month", name="uq_pattern_state_child_month"),
    )
    op.create_index("idx_pattern_state_child", "pattern_state", ["child_id"])


def downgrade() -> None:
    op.drop_index("idx_pattern_state_child", table_name="pattern_state")
    op.drop_table("pattern_state")
