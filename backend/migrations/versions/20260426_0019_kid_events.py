"""Kid-relevant events: auditions, competitions, camps, exams, holidays.

A simple events table the parent can populate manually OR have the
cockpit auto-extract from school messages via LLM. Surfaces on a
dedicated /events page and the Today header for the next 14 days.

Columns:
  child_id      NULL = both kids; otherwise scoped
  event_type    audition | competition | camp | exam | holiday |
                parent_meeting | trip | other
  importance    1 (normal) | 2 (important) | 3 (critical)
  start_date    ISO; required
  end_date      ISO; null = single-day
  start_time    HH:MM; optional
  source        manual | school_message | google_cal | …
  source_ref    text reference to the source (e.g. 'school_message:42')

Revision ID: 0019
Revises: 0018
Create Date: 2026-04-26
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "kid_events",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("child_id", sa.Integer(), sa.ForeignKey("children.id"), nullable=True),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("description", sa.String(), nullable=True),
        sa.Column("event_type", sa.String(), nullable=True),
        sa.Column("importance", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("start_date", sa.String(), nullable=False),
        sa.Column("end_date", sa.String(), nullable=True),
        sa.Column("start_time", sa.String(), nullable=True),
        sa.Column("location", sa.String(), nullable=True),
        sa.Column("source", sa.String(), nullable=False, server_default="manual"),
        sa.Column("source_ref", sa.String(), nullable=True),
        sa.Column("notes", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("idx_kid_events_start", "kid_events", ["start_date"])
    op.create_index("idx_kid_events_child", "kid_events", ["child_id"])
    op.create_index("idx_kid_events_source", "kid_events", ["source"])


def downgrade() -> None:
    op.drop_index("idx_kid_events_source", table_name="kid_events")
    op.drop_index("idx_kid_events_child", table_name="kid_events")
    op.drop_index("idx_kid_events_start", table_name="kid_events")
    op.drop_table("kid_events")
