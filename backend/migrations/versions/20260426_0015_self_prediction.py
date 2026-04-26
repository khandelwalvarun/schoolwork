"""Add self-prediction fields to veracross_items.

Self-prediction loop is a Zimmerman-style metacognition device: before
a test or major assignment, the kid taps a low-bandwidth prediction
("high", "mid", "low" — or a numeric pct band). After the grade lands,
the outcome is computed automatically by comparing actual ≥ predicted
band → "better", within band → "matched", below band → "worse".

The persistent log is a calibration aid: over weeks, the kid (and
parent) can see whether predictions are accurate, optimistic, or
pessimistic. The pedagogy synthesis flagged Zimmerman's loop as the
single highest-leverage metacognition surface; this column makes it
storage-stable.

Columns added to veracross_items:

  self_prediction          str | NULL — "high" | "mid" | "low" | "%xx"
                                       (numeric band like "%85" for 85%)
  self_prediction_set_at   datetime | NULL — when the kid tapped it
  self_prediction_outcome  str | NULL — "matched" | "better" | "worse"

Outcome is derived by services/self_prediction.py once a grade row
links to the assignment via match_grades_to_assignments.

Revision ID: 0015
Revises: 0014
Create Date: 2026-04-26
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "veracross_items",
        sa.Column("self_prediction", sa.String(), nullable=True),
    )
    op.add_column(
        "veracross_items",
        sa.Column(
            "self_prediction_set_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    op.add_column(
        "veracross_items",
        sa.Column("self_prediction_outcome", sa.String(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("veracross_items", "self_prediction_outcome")
    op.drop_column("veracross_items", "self_prediction_set_at")
    op.drop_column("veracross_items", "self_prediction")
