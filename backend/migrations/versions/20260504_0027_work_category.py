"""Add `work_category` to veracross_items + backfill from normalized.type.

The school's Veracross feed already labels every assignment row with a
`type` field — common values: Homework, Classwork, Review, Writing
Skills, Memory and Recall, Logical Reasoning, etc. Until now the
cockpit dropped that signal: everything became `kind="assignment"`,
which meant classwork (already done in class) showed up in overdue /
due_today / upcoming buckets, and reviews didn't get special handling
until a regex on the frontend tried to guess.

This migration adds `work_category` ∈ {classwork, homework, review}
and backfills existing rows from `normalized_json.type` using a
deterministic mapping. New rows get classified by the sync upsert
path going forward (see services/work_category.py).

Revision ID: 0027
Revises: 0026
Create Date: 2026-05-04
"""
from __future__ import annotations

import json

from alembic import op
import sqlalchemy as sa

revision = "0027"
down_revision = "0026"
branch_labels = None
depends_on = None


# Same mapping the runtime classifier uses — duplicated here so the
# migration's backfill is fully self-contained and doesn't import app
# code (which can drift across migration runs).
_TYPE_TO_CATEGORY = {
    "homework": "homework",
    "classwork": "classwork",
    "review": "review",
    # Skill-graded categories the school uses on assessments:
    "memory and recall": "review",
    "logical reasoning": "review",
    "application": "review",
    "computation": "review",
    "comprehension": "review",
    "techniques": "review",
    "grammar and vocabulary": "review",
    "research skills": "review",
    # Skill-graded categories the school uses on creative homework:
    "writing skills": "homework",
    "speaking skills": "homework",
    "reading skills": "homework",
    # Test-shaped types:
    "test": "review",
    "quiz": "review",
    "assessment": "review",
    "exam": "review",
    "examination": "review",
}


def upgrade() -> None:
    op.add_column(
        "veracross_items",
        sa.Column("work_category", sa.String(), nullable=True),
    )
    op.create_index(
        "idx_vc_items_work_category",
        "veracross_items",
        ["work_category"],
    )

    # Backfill existing assignment rows from normalized_json.type.
    # Every row gets tagged — unmapped/missing types default to
    # `homework` (the most actionable bucket). Unmapped values are
    # printed at the end so the mapping can be extended.
    bind = op.get_bind()
    rows = list(bind.execute(
        sa.text(
            "SELECT id, normalized_json FROM veracross_items "
            "WHERE kind = 'assignment'"
        )
    ).fetchall())
    classified = 0
    defaulted_no_type = 0
    unmapped: dict[str, int] = {}
    for r in rows:
        try:
            normalized = json.loads(r.normalized_json or "{}")
        except Exception:
            normalized = {}
        raw_type = (normalized.get("type") or "").strip()
        if not raw_type:
            defaulted_no_type += 1
            category = "homework"
        else:
            category = _TYPE_TO_CATEGORY.get(raw_type.lower())
            if category is None:
                unmapped[raw_type] = unmapped.get(raw_type, 0) + 1
                category = "homework"
        bind.execute(
            sa.text("UPDATE veracross_items SET work_category = :c WHERE id = :i"),
            {"c": category, "i": r.id},
        )
        classified += 1
    if classified:
        print(f"  → tagged {classified} assignment rows")
    if defaulted_no_type:
        print(f"  → {defaulted_no_type} had no `type` — defaulted to homework")
    if unmapped:
        print(f"  → {sum(unmapped.values())} unmapped types defaulted to homework: {unmapped}")
        print("    Extend _TYPE_TO_CATEGORY in services/work_category.py to cover them.")


def downgrade() -> None:
    op.drop_index("idx_vc_items_work_category", table_name="veracross_items")
    op.drop_column("veracross_items", "work_category")
