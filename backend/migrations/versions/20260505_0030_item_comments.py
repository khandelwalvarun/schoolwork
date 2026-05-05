"""Per-item parent comments — free-form notes attached to a specific
assignment, review, grade or comment row.

Why this exists:
  Until now the cockpit had no place for the parent to record an
  observation against a specific piece of work — "Tejas got stuck on
  the third question because he didn't read the directions", or "this
  was the second short-answer test in a row where he ran out of time".
  Such observations are gold for pattern detection — but only if they
  live in a structured place an LLM can later aggregate and slice.

  ParentNote (parent_notes) is child-scoped and dated, not item-scoped.
  It can't answer "show me every comment on a Math review in the last
  6 weeks" or "are there recurring themes in my comments on Hindi
  homework?". This new table can.

Schema notes:
  - `item_id` is the foreign-key into veracross_items (any kind:
     assignment, grade, comment, school_message). Many comments per
     item is normal — comments accumulate over time.
  - `child_id` is denormalised so aggregate queries don't have to
     join through veracross_items every time.
  - `subject` is denormalised for the same reason — most aggregation
     slices are subject-shaped.
  - `body` is free-form text. Optional `sentiment` ∈ {'positive',
     'neutral', 'concern'} and JSON `tags` give the parent a one-tap
     handle for "is this a win or a worry"; the LLM aggregation can
     stratify by these.
  - `topic` is an optional fine-grained label like 'fractions' or
     'writing organization' — used by future LLM passes to cluster.

Revision ID: 0030
Revises: 0029
Create Date: 2026-05-05
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0030"
down_revision = "0029"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "item_comments",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column(
            "item_id",
            sa.Integer,
            sa.ForeignKey("veracross_items.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "child_id",
            sa.Integer,
            sa.ForeignKey("children.id"),
            nullable=False,
        ),
        sa.Column("subject", sa.String, nullable=True),
        sa.Column("body", sa.Text, nullable=False),
        sa.Column("sentiment", sa.String, nullable=True),
        sa.Column("topic", sa.String, nullable=True),
        sa.Column("tags_json", sa.Text, nullable=True),
        sa.Column("author", sa.String, nullable=False, server_default="parent"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "idx_item_comments_item", "item_comments", ["item_id"],
    )
    op.create_index(
        "idx_item_comments_child_subject",
        "item_comments",
        ["child_id", "subject"],
    )
    op.create_index(
        "idx_item_comments_created", "item_comments", ["created_at"],
    )


def downgrade() -> None:
    op.drop_index("idx_item_comments_created", table_name="item_comments")
    op.drop_index("idx_item_comments_child_subject", table_name="item_comments")
    op.drop_index("idx_item_comments_item", table_name="item_comments")
    op.drop_table("item_comments")
