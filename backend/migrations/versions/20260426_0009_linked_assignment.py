"""Add linked_assignment_id + match_confidence + match_method to veracross_items.

Lets a grade row point at the assignment it grades. The cockpit
matches grade ↔ assignment via deterministic Jaccard similarity
first (free, fast), falling back to a local LLM (Ollama) when the
top two candidates are within a small confidence margin.

  linked_assignment_id  → veracross_items.id of the matched assignment
  match_confidence      → 0.0..1.0
  match_method          → 'jaccard' | 'llm' | 'manual'

Revision ID: 0009
Revises: 0008
Create Date: 2026-04-26
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("veracross_items") as batch:
        batch.add_column(sa.Column("linked_assignment_id", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("match_confidence", sa.Float(), nullable=True))
        batch.add_column(sa.Column("match_method", sa.String(), nullable=True))
    op.create_index(
        "idx_vc_items_linked_assignment",
        "veracross_items",
        ["linked_assignment_id"],
    )


def downgrade() -> None:
    op.drop_index("idx_vc_items_linked_assignment", table_name="veracross_items")
    with op.batch_alter_table("veracross_items") as batch:
        batch.drop_column("match_method")
        batch.drop_column("match_confidence")
        batch.drop_column("linked_assignment_id")
