"""Add parent_marked_submitted_at to veracross_items — parent override for late-grading teachers.

Revision ID: 0002
Revises: 0001
Create Date: 2026-04-23
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("veracross_items") as batch:
        batch.add_column(
            sa.Column("parent_marked_submitted_at", sa.DateTime(timezone=True), nullable=True)
        )


def downgrade() -> None:
    with op.batch_alter_table("veracross_items") as batch:
        batch.drop_column("parent_marked_submitted_at")
