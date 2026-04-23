"""Syllabus calibration — cycle-boundary + topic-status overrides.

Revision ID: 0003
Revises: 0002
Create Date: 2026-04-23
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "syllabus_cycle_overrides",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("class_level", sa.Integer, nullable=False),
        sa.Column("cycle_name", sa.String, nullable=False),
        sa.Column("start_date", sa.String, nullable=True),  # ISO date
        sa.Column("end_date", sa.String, nullable=True),
        sa.Column("note", sa.String, nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("class_level", "cycle_name", name="uq_syl_cycle_override"),
    )

    op.create_table(
        "syllabus_topic_status",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("class_level", sa.Integer, nullable=False),
        sa.Column("subject", sa.String, nullable=False),
        sa.Column("topic", sa.String, nullable=False),
        sa.Column("status", sa.String, nullable=False),  # covered | skipped | delayed | in_progress
        sa.Column("note", sa.String, nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("class_level", "subject", "topic", name="uq_syl_topic_status"),
    )


def downgrade() -> None:
    op.drop_table("syllabus_topic_status")
    op.drop_table("syllabus_cycle_overrides")
