"""Persist LLM-driven free-form analyses.

The parent asks open-ended questions about their kids' work via the
/analysis page; the LLM pulls together relevant data (grades,
assignments, comments, patterns, anomalies, mindspark, recent
messages) and returns a structured response. Each one is persisted
so the parent can revisit / share / build on prior analyses.

Revision ID: 0026
Revises: 0025
Create Date: 2026-05-04
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0026"
down_revision = "0025"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "llm_analysis",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        # Optional child scope. NULL = analysis spans both kids.
        sa.Column(
            "child_id", sa.Integer(),
            sa.ForeignKey("children.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("query", sa.String(), nullable=False),
        sa.Column("scope_days", sa.Integer(), nullable=False, server_default="30"),
        # Output_md is the printable / scrollable summary; output_json
        # is the structured form the UI renders into chips and lists.
        sa.Column("output_md", sa.String(), nullable=True),
        sa.Column("output_json", sa.String(), nullable=True),
        sa.Column("llm_used", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("llm_model", sa.String(), nullable=True),
        sa.Column("llm_input_tokens", sa.Integer(), nullable=True),
        sa.Column("llm_output_tokens", sa.Integer(), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("error", sa.String(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
    )
    op.create_index(
        "idx_llm_analysis_child_created",
        "llm_analysis", ["child_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("idx_llm_analysis_child_created", table_name="llm_analysis")
    op.drop_table("llm_analysis")
