"""Mindspark — narrow performance-metrics scrape.

Scope (intentional, do not expand without user re-confirmation):

  WHAT WE STORE:
    - per-session aggregate metrics (started_at, duration_sec,
      questions_total, questions_correct, accuracy_pct, subject)
    - per-topic progress snapshots (subject, topic_name, accuracy_pct,
      attempts, last_activity_at, mastery_level)

  WHAT WE EXPLICITLY DO NOT STORE:
    - question content (stems, options, explanations)
    - answer text
    - student responses
    - any pedagogical IP

This is a personal-use parental monitoring scraper. We pull only the
parent-facing dashboard surfaces and run at a slow rate (≥30s between
pages, daily cadence). The kid's full session content stays inside
Ei's platform.

Revision ID: 0020
Revises: 0019
Create Date: 2026-04-26
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "mindspark_session",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("child_id", sa.Integer(), sa.ForeignKey("children.id"), nullable=False),
        sa.Column("external_id", sa.String(), nullable=False),  # mindspark sessionId
        sa.Column("subject", sa.String(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_sec", sa.Integer(), nullable=True),
        sa.Column("questions_total", sa.Integer(), nullable=True),
        sa.Column("questions_correct", sa.Integer(), nullable=True),
        sa.Column("accuracy_pct", sa.Float(), nullable=True),
        sa.Column("topic_name", sa.String(), nullable=True),  # if session was topic-scoped
        sa.Column("raw_json", sa.String(), nullable=True),    # for debugging only
        sa.Column("seen_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("child_id", "external_id", name="uq_ms_session_child_extid"),
    )
    op.create_index("idx_ms_session_child", "mindspark_session", ["child_id"])
    op.create_index("idx_ms_session_started", "mindspark_session", ["started_at"])

    op.create_table(
        "mindspark_topic_progress",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("child_id", sa.Integer(), sa.ForeignKey("children.id"), nullable=False),
        sa.Column("subject", sa.String(), nullable=False),
        sa.Column("topic_id", sa.String(), nullable=True),    # mindspark's id when present
        sa.Column("topic_name", sa.String(), nullable=False),
        sa.Column("accuracy_pct", sa.Float(), nullable=True),
        sa.Column("questions_attempted", sa.Integer(), nullable=True),
        sa.Column("time_spent_sec", sa.Integer(), nullable=True),
        sa.Column("mastery_level", sa.String(), nullable=True),  # verbatim from mindspark
        sa.Column("last_activity_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("raw_json", sa.String(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint(
            "child_id", "subject", "topic_name",
            name="uq_ms_topic_child_subj_name",
        ),
    )
    op.create_index("idx_ms_topic_child", "mindspark_topic_progress", ["child_id"])
    op.create_index("idx_ms_topic_subject", "mindspark_topic_progress", ["subject"])


def downgrade() -> None:
    op.drop_index("idx_ms_topic_subject", table_name="mindspark_topic_progress")
    op.drop_index("idx_ms_topic_child", table_name="mindspark_topic_progress")
    op.drop_table("mindspark_topic_progress")
    op.drop_index("idx_ms_session_started", table_name="mindspark_session")
    op.drop_index("idx_ms_session_child", table_name="mindspark_session")
    op.drop_table("mindspark_session")
