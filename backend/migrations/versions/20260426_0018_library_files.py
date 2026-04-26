"""Library: parent-uploaded files (textbooks, references, study material).

Distinct from the existing `attachments` table (which carries scraped
Veracross attachments + portfolio uploads tied to topics): this is a
free-form per-kid (or shared) library where the parent drops PDFs,
worksheets, scanned newsletters, and similar. An LLM (claude_cli)
inspects the filename + extracted text and fills in the `llm_*`
columns: kind, subject, class_level, 2-3 sentence summary, keywords.

Storage on disk: data/library/<sha-prefix>/<filename>. SHA-256 dedup
on the column means re-uploading the same file silently keeps a
single row.

Revision ID: 0018
Revises: 0017
Create Date: 2026-04-26
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "library_files",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("filename", sa.String(), nullable=False),
        sa.Column("original_filename", sa.String(), nullable=True),
        sa.Column("sha256", sa.String(), nullable=False, unique=True),
        sa.Column("size_bytes", sa.Integer(), nullable=True),
        sa.Column("mime_type", sa.String(), nullable=True),
        sa.Column("local_path", sa.String(), nullable=False),
        sa.Column("child_id", sa.Integer(), sa.ForeignKey("children.id"), nullable=True),
        sa.Column("uploaded_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("note", sa.String(), nullable=True),
        # LLM classification — nullable until processed
        sa.Column("llm_kind", sa.String(), nullable=True),
        sa.Column("llm_subject", sa.String(), nullable=True),
        sa.Column("llm_class_level", sa.Integer(), nullable=True),
        sa.Column("llm_summary", sa.String(), nullable=True),
        sa.Column("llm_keywords", sa.String(), nullable=True),  # JSON-encoded list
        sa.Column("llm_processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("llm_model", sa.String(), nullable=True),
        sa.Column("llm_error", sa.String(), nullable=True),
    )
    op.create_index("idx_library_files_child", "library_files", ["child_id"])
    op.create_index("idx_library_files_kind", "library_files", ["llm_kind"])
    op.create_index("idx_library_files_subject", "library_files", ["llm_subject"])


def downgrade() -> None:
    op.drop_index("idx_library_files_subject", table_name="library_files")
    op.drop_index("idx_library_files_kind", table_name="library_files")
    op.drop_index("idx_library_files_child", table_name="library_files")
    op.drop_table("library_files")
