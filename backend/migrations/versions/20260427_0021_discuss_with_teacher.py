"""Add `discuss_with_teacher_at` flag to assignments.

The parent can mark any assignment as "worth a chat" — an item that's
already done/graded but they want to raise it at the next parent-teacher
meeting (a low-score they don't understand, an interesting topic the
kid loved, an instruction that wasn't clear, etc.).

Two columns:
  discuss_with_teacher_at    timestamp the parent flagged it (NULL = unflagged)
  discuss_with_teacher_note  optional reason ("ask why score dropped",
                              "praise topic choice", etc.)

The PTM brief consumes these flags as a dedicated "Worth a chat"
subsection per subject so the parent walks into the meeting with their
own questions, not just Claude-generated ones.

Symmetrical with `parent_marked_submitted_at` — timestamp = on,
NULL = off — so we get a free history of when each item was flagged
without needing an extra audit table (the audit-history row is still
written in services/assignment_state.py).

Revision ID: 0021
Revises: 0020
Create Date: 2026-04-27
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0021"
down_revision = "0020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "veracross_items",
        sa.Column("discuss_with_teacher_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "veracross_items",
        sa.Column("discuss_with_teacher_note", sa.String(), nullable=True),
    )
    # Most queries filter on "is the flag set?" so a partial-style index
    # on the timestamp itself is enough — SQLite will use it for
    # IS NOT NULL probes.
    op.create_index(
        "idx_vc_items_discuss_at",
        "veracross_items",
        ["discuss_with_teacher_at"],
    )


def downgrade() -> None:
    op.drop_index("idx_vc_items_discuss_at", table_name="veracross_items")
    op.drop_column("veracross_items", "discuss_with_teacher_note")
    op.drop_column("veracross_items", "discuss_with_teacher_at")
