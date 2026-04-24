"""Attachments table — downloaded files referenced by assignments / messages.

Revision ID: 0004
Revises: 0003
Create Date: 2026-04-23
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "attachments",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("item_id", sa.Integer, sa.ForeignKey("veracross_items.id"), nullable=True),
        sa.Column("child_id", sa.Integer, sa.ForeignKey("children.id"), nullable=True),
        sa.Column("filename", sa.String, nullable=False),
        sa.Column("original_url", sa.String, nullable=False),
        sa.Column("local_path", sa.String, nullable=False),
        sa.Column("mime_type", sa.String, nullable=True),
        sa.Column("size_bytes", sa.Integer, nullable=True),
        sa.Column("sha256", sa.String, nullable=False),
        sa.Column("kind", sa.String, nullable=True),  # syllabus | booklist | spelling | homework | ...
        sa.Column("source_kind", sa.String, nullable=False),  # assignment | school_message | resource
        sa.Column("note", sa.String, nullable=True),
        sa.Column(
            "downloaded_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "last_seen_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("item_id", "sha256", name="uq_attachments_item_sha"),
    )
    op.create_index("idx_attachments_item", "attachments", ["item_id"])
    op.create_index("idx_attachments_sha", "attachments", ["sha256"])


def downgrade() -> None:
    op.drop_index("idx_attachments_sha", table_name="attachments")
    op.drop_index("idx_attachments_item", table_name="attachments")
    op.drop_table("attachments")
