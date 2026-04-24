"""Add log_text to sync_runs so each run keeps an in-line log we can
show in the frontend. Pruned weekly via the retention job.

Revision ID: 0007
Revises: 0006
Create Date: 2026-04-24
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("sync_runs") as batch:
        batch.add_column(sa.Column("log_text", sa.String, nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("sync_runs") as batch:
        batch.drop_column("log_text")
