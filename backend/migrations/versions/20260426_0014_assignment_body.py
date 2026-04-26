"""Add `body` column to veracross_items.

The Veracross homework popup carries a multi-paragraph description on
most assignments (the "Notes" field on the detail page). The scraper
already parsed this — `parse_assignment_detail()` returned `notes` and
the enrichment branch even put it in `normalized_json["body"]` — but
the back-fill pass at sync.py:489-500 only looked at it as a
translation source. When the body was already English, the value was
dropped entirely. Result: parents never saw the description.

Phase-12.5 fix: persist `body` as a queryable column so it survives the
detail-fetch path regardless of language. `notes_en` stays semantically
"translated-to-English notes" — we don't reuse it because the
translator job depends on that invariant.

Revision ID: 0014
Revises: 0013
Create Date: 2026-04-26
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "veracross_items",
        sa.Column("body", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("veracross_items", "body")
