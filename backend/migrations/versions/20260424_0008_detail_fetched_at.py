"""Add detail_fetched_at timestamp to veracross_items.

Lets the attachment pass skip items that have already been checked —
key to the new tiered sync: light tier never re-fetches stable detail
pages, medium tier repairs stale ones (>24h), heavy tier rebuilds all.

Revision ID: 0008
Revises: 0007
Create Date: 2026-04-24
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("veracross_items") as batch:
        batch.add_column(sa.Column("detail_fetched_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("veracross_items") as batch:
        batch.drop_column("detail_fetched_at")
