"""Add language_code to topic_state.

Vasant Valley teaches three language tracks side-by-side:
  English   the medium of instruction; most non-language subjects too
  Hindi     mandatory second language; a separate textbook + cycle
  Sanskrit  third language for some classes; rarer, smaller corpus

The cockpit's grade trends and topic-state lists currently mix all
three into one stack. The pedagogy synthesis flagged this — a kid's
Hindi vocabulary trajectory is independent of their English reading
trajectory and shouldn't average into one number.

Phase 15 attaches a language code to each TopicState row so the
syllabus + grade-trend surfaces can split or filter by language.
The code is one of:

  en   English (default)
  hi   Hindi
  sa   Sanskrit
  NULL not yet classified (legacy rows; backfill is a follow-up)

Backfill happens via `services/language.py:language_code_for()` which
matches against subject substrings ('Hindi', 'Sanskrit', etc.).

Revision ID: 0013
Revises: 0012
Create Date: 2026-04-26
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "topic_state",
        sa.Column("language_code", sa.String(), nullable=True),
    )
    op.create_index(
        "idx_topic_state_lang", "topic_state", ["language_code"],
    )


def downgrade() -> None:
    op.drop_index("idx_topic_state_lang", table_name="topic_state")
    op.drop_column("topic_state", "language_code")
