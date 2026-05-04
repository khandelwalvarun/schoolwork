"""Add `kind` discriminator to practice_session.

Two flavours of session, sharing the same iteration + scan plumbing:

  review_prep      — generates a practice sheet of questions for an
                     upcoming review/test (the original mode)
  assignment_help  — generates support material for an existing
                     assignment: outline, worked-example, hints,
                     reading guide, brainstorm starter, etc.

Both use the same iterate flow and Claude Opus call. The `kind` column
just lets the LLM pick the right system prompt and the renderer pick
the right output schema. Default is "review_prep" so existing rows
continue to behave the same way.

Revision ID: 0023
Revises: 0022
Create Date: 2026-05-04
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0023"
down_revision = "0022"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "practice_session",
        sa.Column(
            "kind", sa.String(),
            nullable=False,
            server_default="review_prep",
        ),
    )
    op.create_index(
        "idx_practice_session_kind", "practice_session", ["kind"],
    )


def downgrade() -> None:
    op.drop_index("idx_practice_session_kind", table_name="practice_session")
    op.drop_column("practice_session", "kind")
