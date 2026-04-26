"""Add (topic_subject, topic_topic) to attachments — portfolio support.

Phase 20 lets the parent attach a photo / scan / drawing to a syllabus
topic so the kid's record gains a "portfolio" dimension beyond the
school's own gradebook. Examples: a phone photo of a science-fair
poster, a scan of a hand-drawn map for social-science, a screen capture
of an in-class project.

Storage choice: bind to the *natural key* (subject, topic) rather than
an FK to topic_state.id. topic_state rows get wiped + rebuilt on every
nightly recompute, so an FK there would break repeatedly. Subject +
topic strings are stable across recomputes (the syllabus changes rarely).

Existing attachment fields:
  item_id    set when the attachment came from a Veracross item
  child_id   the kid this belongs to
  source_kind how it landed (download, upload_homework, etc.)

New fields (nullable so legacy rows are unaffected):
  topic_subject  string (the subject name, e.g. "6B English")
  topic_topic    string (the topic name, e.g. "LC1: Friend's Prayer")

Revision ID: 0016
Revises: 0015
Create Date: 2026-04-26
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "attachments",
        sa.Column("topic_subject", sa.String(), nullable=True),
    )
    op.add_column(
        "attachments",
        sa.Column("topic_topic", sa.String(), nullable=True),
    )
    op.create_index(
        "idx_attachments_topic",
        "attachments",
        ["child_id", "topic_subject", "topic_topic"],
    )


def downgrade() -> None:
    op.drop_index("idx_attachments_topic", table_name="attachments")
    op.drop_column("attachments", "topic_topic")
    op.drop_column("attachments", "topic_subject")
