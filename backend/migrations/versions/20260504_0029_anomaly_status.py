"""Per-grade anomaly status (open / dismissed / escalated / reviewed).

The off-trend detector flags grades and Claude writes a hypothesis to
`llm_summary`, but until now there was no way for the parent to clear a
flag once they'd seen it. The Today banner kept re-showing every
historic anomaly forever.

This migration adds:
  - `anomaly_status` ∈ {None, 'open', 'dismissed', 'escalated', 'reviewed'}
  - `anomaly_status_at` — when the parent last set the status

Backfills every existing anomalous grade as 'open'. The auto-explainer
job will pre-warm hypotheses for these so the UI doesn't have to wait
on the first read.

Revision ID: 0029
Revises: 0028
Create Date: 2026-05-04
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0029"
down_revision = "0028"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "veracross_items",
        sa.Column("anomaly_status", sa.String(), nullable=True),
    )
    op.add_column(
        "veracross_items",
        sa.Column("anomaly_status_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "idx_vc_items_anomaly_status",
        "veracross_items",
        ["anomaly_status"],
    )


def downgrade() -> None:
    op.drop_index("idx_vc_items_anomaly_status", table_name="veracross_items")
    op.drop_column("veracross_items", "anomaly_status_at")
    op.drop_column("veracross_items", "anomaly_status")
