"""Add topic_state table — per-(child × class × subject × topic) mastery row.

Computed from grades + assignments tagged to each syllabus topic via
the existing `fuzzy_topic_for` matcher. State follows Khan Academy's
heuristics + Cepeda's spacing rule for decay.

  state                      — attempted | familiar | proficient | mastered | decaying
  last_assessed_at           — date of latest contributing item (graded date or due date)
  last_score                 — most recent grade % (nullable)
  attempt_count              — total items contributing
  proficient_count           — consecutive items at ≥ 75 %

Revision ID: 0010
Revises: 0009
Create Date: 2026-04-26
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "topic_state",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("child_id", sa.Integer(), sa.ForeignKey("children.id"), nullable=False),
        sa.Column("class_level", sa.Integer(), nullable=False),
        sa.Column("subject", sa.String(), nullable=False),
        sa.Column("topic", sa.String(), nullable=False),
        sa.Column("state", sa.String(), nullable=False),
        sa.Column("last_assessed_at", sa.String(), nullable=True),
        sa.Column("last_score", sa.Float(), nullable=True),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("proficient_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("child_id", "class_level", "subject", "topic", name="uq_topic_state"),
    )
    op.create_index("idx_topic_state_child", "topic_state", ["child_id"])


def downgrade() -> None:
    op.drop_index("idx_topic_state_child", table_name="topic_state")
    op.drop_table("topic_state")
