"""Professional status tracking: parent_status enum, priority, snooze,
status_notes, tags_json on veracross_items + assignment_status_history table.

Revision ID: 0006
Revises: 0005
Create Date: 2026-04-24
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("veracross_items") as batch:
        batch.add_column(sa.Column("parent_status", sa.String, nullable=True))
        batch.add_column(sa.Column(
            "priority", sa.Integer, nullable=False, server_default="0"
        ))
        batch.add_column(sa.Column("snooze_until", sa.String, nullable=True))
        batch.add_column(sa.Column("status_notes", sa.String, nullable=True))
        batch.add_column(sa.Column("tags_json", sa.String, nullable=True))
    # Backfill parent_status from the old parent_marked_submitted_at flag.
    op.execute(
        "UPDATE veracross_items SET parent_status = 'submitted' "
        "WHERE parent_marked_submitted_at IS NOT NULL AND parent_status IS NULL"
    )

    op.create_table(
        "assignment_status_history",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("item_id", sa.Integer, sa.ForeignKey("veracross_items.id"), nullable=False),
        sa.Column("field", sa.String, nullable=False),           # e.g. parent_status, priority, snooze_until, tags, portal_status
        sa.Column("old_value", sa.String, nullable=True),
        sa.Column("new_value", sa.String, nullable=True),
        sa.Column("source", sa.String, nullable=False),          # 'parent' | 'portal' | 'system'
        sa.Column("actor", sa.String, nullable=True),            # free text (e.g. 'varun', 'scraper', 'scheduler')
        sa.Column("note", sa.String, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "idx_asg_status_hist_item", "assignment_status_history", ["item_id", "created_at"]
    )


def downgrade() -> None:
    op.drop_index("idx_asg_status_hist_item", table_name="assignment_status_history")
    op.drop_table("assignment_status_history")
    with op.batch_alter_table("veracross_items") as batch:
        batch.drop_column("tags_json")
        batch.drop_column("status_notes")
        batch.drop_column("snooze_until")
        batch.drop_column("priority")
        batch.drop_column("parent_status")
