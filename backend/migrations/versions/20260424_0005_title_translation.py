"""Add title_en + notes_en to veracross_items for English translations of
non-Latin titles (Hindi, Sanskrit) discovered on detail pages.

Revision ID: 0005
Revises: 0004
Create Date: 2026-04-24
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("veracross_items") as batch:
        batch.add_column(sa.Column("title_en", sa.String, nullable=True))
        batch.add_column(sa.Column("notes_en", sa.String, nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("veracross_items") as batch:
        batch.drop_column("notes_en")
        batch.drop_column("title_en")
