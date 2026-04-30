"""Practice-prep sessions — iterative LLM-driven test/review prep with
classwork-scan grounding.

Three tables:

  practice_session
    A persistent prep workspace. One session typically corresponds to
    one upcoming review/test, but the parent can also start a free-form
    session (subject + topic, no linked assignment). Each session
    accumulates iterations the parent steered with prompts, plus
    classwork scans the parent uploaded to ground the LLM.

  practice_iteration
    One generated draft. Each iteration carries the parent's prompt
    that produced it (None for the initial generation), the model
    used, the markdown output, and the parsed-out JSON so the UI can
    render question-level affordances. Parent can star one as
    `preferred` — that's the version printed for the kid.

  practice_classwork_scan
    A photo / scan / PDF the parent uploaded showing what was actually
    covered in class. Claude Vision extracts the text + summary at
    upload time so the practice generator can use it as grounding
    context without re-OCR'ing on every iteration.

This is the (b) backbone — the UI workspace + nightly auto-generation
land in subsequent migrations / commits. Reachable via MCP from day
one so the prompt design can be exercised before any UI is built.

Revision ID: 0022
Revises: 0021
Create Date: 2026-04-30
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0022"
down_revision = "0021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "practice_session",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("child_id", sa.Integer(), sa.ForeignKey("children.id"), nullable=False),
        sa.Column("subject", sa.String(), nullable=False),
        sa.Column("topic", sa.String(), nullable=True),
        # Optional: link to the upcoming review/test that triggered this prep.
        # The session survives even if the source row is later deleted.
        sa.Column(
            "linked_assignment_id", sa.Integer(),
            sa.ForeignKey("veracross_items.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="active"),
        sa.Column("preferred_iteration_id", sa.Integer(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "idx_practice_session_child", "practice_session", ["child_id"],
    )
    op.create_index(
        "idx_practice_session_subject", "practice_session", ["subject"],
    )
    op.create_index(
        "idx_practice_session_linked", "practice_session", ["linked_assignment_id"],
    )

    op.create_table(
        "practice_iteration",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "session_id", sa.Integer(),
            sa.ForeignKey("practice_session.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("iteration_index", sa.Integer(), nullable=False),
        # The parent's prompt that drove THIS iteration. NULL for the
        # initial generation (which used the session's defaults).
        sa.Column("parent_prompt", sa.String(), nullable=True),
        # What the LLM actually produced.
        sa.Column("output_md", sa.String(), nullable=False),
        # Parsed structured form: {questions: [{n, stem, type, marks,
        # expected_answer, expected_solution_md, topic_ref}], answer_key,
        # honest_caveat}. Stored as JSON string for SQLite portability.
        sa.Column("output_json", sa.String(), nullable=True),
        # Honesty: did we actually hit the LLM, or did we fall through
        # to the rule skeleton? `false` means we hand-rolled placeholders
        # because the LLM was unreachable.
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
        sa.UniqueConstraint(
            "session_id", "iteration_index",
            name="uq_practice_iteration_session_idx",
        ),
    )
    op.create_index(
        "idx_practice_iteration_session", "practice_iteration", ["session_id"],
    )

    op.create_table(
        "practice_classwork_scan",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        # Scans can be uploaded freestanding (child + subject only)
        # and later linked to a session, so session_id is nullable.
        sa.Column(
            "session_id", sa.Integer(),
            sa.ForeignKey("practice_session.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "child_id", sa.Integer(),
            sa.ForeignKey("children.id"), nullable=False,
        ),
        sa.Column("subject", sa.String(), nullable=False),
        # Storage lives in the existing `attachments` table (source_kind=
        # 'practice_classwork') so we get dedup + path-resolution for free.
        sa.Column(
            "attachment_id", sa.Integer(),
            sa.ForeignKey("attachments.id", ondelete="CASCADE"),
            nullable=False,
        ),
        # Cache of the Vision/OCR pass so we don't re-extract on every
        # iteration. Empty string = extraction not yet attempted; NULL
        # means "tried, got nothing".
        sa.Column("extracted_text", sa.String(), nullable=True),
        sa.Column("extracted_summary", sa.String(), nullable=True),
        sa.Column("extracted_topics_json", sa.String(), nullable=True),
        sa.Column("extracted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "uploaded_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
        sa.UniqueConstraint("attachment_id", name="uq_practice_scan_attachment"),
    )
    op.create_index(
        "idx_practice_scan_child_subject",
        "practice_classwork_scan", ["child_id", "subject"],
    )
    op.create_index(
        "idx_practice_scan_session", "practice_classwork_scan", ["session_id"],
    )


def downgrade() -> None:
    op.drop_index("idx_practice_scan_session", table_name="practice_classwork_scan")
    op.drop_index("idx_practice_scan_child_subject", table_name="practice_classwork_scan")
    op.drop_table("practice_classwork_scan")
    op.drop_index("idx_practice_iteration_session", table_name="practice_iteration")
    op.drop_table("practice_iteration")
    op.drop_index("idx_practice_session_linked", table_name="practice_session")
    op.drop_index("idx_practice_session_subject", table_name="practice_session")
    op.drop_index("idx_practice_session_child", table_name="practice_session")
    op.drop_table("practice_session")
