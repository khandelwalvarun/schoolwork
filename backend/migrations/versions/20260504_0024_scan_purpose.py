"""Add `purpose` to practice_classwork_scan.

Two purposes share the same scan table + Vision pipeline:

  classwork_reference  — photo of recent classwork, used as grounding
                         context for the practice generator (what's
                         been covered in class)
  student_work         — photo of the kid's COMPLETED assignment,
                         submitted for the LLM to check / mark / give
                         feedback on (kind=review_work session)

The classwork-reference flow is the existing one (default for back-
compat). student_work is new — pairs with KIND_REVIEW_WORK on
practice_session and a different Vision prompt that asks the LLM to
transcribe what the kid actually wrote, not summarise the lesson.

Revision ID: 0024
Revises: 0023
Create Date: 2026-05-04
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0024"
down_revision = "0023"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "practice_classwork_scan",
        sa.Column(
            "purpose", sa.String(),
            nullable=False,
            server_default="classwork_reference",
        ),
    )
    op.create_index(
        "idx_practice_scan_purpose",
        "practice_classwork_scan",
        ["purpose"],
    )


def downgrade() -> None:
    op.drop_index("idx_practice_scan_purpose", table_name="practice_classwork_scan")
    op.drop_column("practice_classwork_scan", "purpose")
