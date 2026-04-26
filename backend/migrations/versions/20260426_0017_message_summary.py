"""Add llm_summary column to veracross_items.

Phase 22 — for school messages, the parent often gets two near-identical
notifications (one per kid). The dedup view groups them by normalized
title and stores one LLM-generated 1-sentence summary across the group.

Revision ID: 0017
Revises: 0016
Create Date: 2026-04-26
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "veracross_items",
        sa.Column("llm_summary", sa.String(), nullable=True),
    )
    op.add_column(
        "veracross_items",
        sa.Column("llm_summary_url", sa.String(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("veracross_items", "llm_summary_url")
    op.drop_column("veracross_items", "llm_summary")
