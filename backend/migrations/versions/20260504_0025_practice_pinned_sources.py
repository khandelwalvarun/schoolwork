"""Add `pinned_sources_json` to practice_session.

Lets the parent pin specific grounding context to a session — a
textbook PDF from the library, a Spelling Bee word list from the
portal-harvested resources, or specific syllabus topics they want
the LLM to focus on. Each pinned source feeds extracted content into
the data pack on every iteration.

Stored as a JSON array of {type, ref, label} dicts:
  type: "library" | "resource" | "syllabus_topic"
  ref:  library_id (int) | "scope/category/filename" (str) | topic name (str)
  label: human-readable string the UI shows on the pinned-source chip

Revision ID: 0025
Revises: 0024
Create Date: 2026-05-04
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0025"
down_revision = "0024"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "practice_session",
        sa.Column("pinned_sources_json", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("practice_session", "pinned_sources_json")
