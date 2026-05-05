"""Translation cache — content-addressed by sha256(text) + target_lang.

Many Hindi/Sanskrit titles repeat across days, kids and runs (e.g.
"पाठ ५ का अभ्यास" or "स्वर संधि"). Today every occurrence ends up
calling Opus through `translate_to_english`, even though the result
would be byte-identical to a previous call. This wastes spend.

This migration adds a tiny key-value table keyed on (sha256, target).
The translate service consults the cache before calling the LLM and
writes the result back on success.

Revision ID: 0028
Revises: 0027
Create Date: 2026-05-04
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0028"
down_revision = "0027"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "translation_cache",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("text_sha256", sa.String, nullable=False),
        sa.Column("target_lang", sa.String, nullable=False),
        sa.Column("source_text", sa.Text, nullable=False),
        sa.Column("translated_text", sa.Text, nullable=False),
        sa.Column("model", sa.String, nullable=True),
        sa.Column("hits", sa.Integer, nullable=False, server_default="1"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "last_used_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint(
            "text_sha256", "target_lang", name="uq_translation_cache_key"
        ),
    )
    op.create_index(
        "idx_translation_cache_lookup",
        "translation_cache",
        ["text_sha256", "target_lang"],
    )


def downgrade() -> None:
    op.drop_index(
        "idx_translation_cache_lookup", table_name="translation_cache"
    )
    op.drop_table("translation_cache")
