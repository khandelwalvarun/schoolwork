"""Add tier / rule_id / why_json + snooze table to notifications.

Three tiers govern *when* a notification fires:

  now      fires immediately across enabled channels (telegram, email,
           inapp) subject to existing rate limits and threshold gates.
  today    inapp only at fire time; rolled into the morning digest for
           email + telegram.
  weekly   inapp only, deferred to the weekly digest.

`rule_id` and `why_json` carry the explanation payload — what rule
triggered + which datapoints crossed the threshold. The (why?) link
on the Notifications page reads these to render a small popover.

A separate `notification_snooze` table holds per-rule snoozes the
parent set from the (why?) popover. The dispatcher consults this
table at fire time and suppresses with reason "snoozed by parent".

Revision ID: 0012
Revises: 0011
Create Date: 2026-04-26
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "notifications",
        sa.Column("tier", sa.String(), nullable=True),
    )
    op.add_column(
        "notifications",
        sa.Column("rule_id", sa.String(), nullable=True),
    )
    op.add_column(
        "notifications",
        sa.Column("why_json", sa.String(), nullable=True),
    )
    op.create_index(
        "idx_notif_rule_id", "notifications", ["rule_id"],
    )

    op.create_table(
        "notification_snooze",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("rule_id", sa.String(), nullable=False),
        sa.Column("child_id", sa.Integer(), sa.ForeignKey("children.id"), nullable=True),
        sa.Column("until", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reason", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("rule_id", "child_id", name="uq_notif_snooze_rule_child"),
    )
    op.create_index(
        "idx_notif_snooze_rule", "notification_snooze", ["rule_id"],
    )


def downgrade() -> None:
    op.drop_index("idx_notif_snooze_rule", table_name="notification_snooze")
    op.drop_table("notification_snooze")
    op.drop_index("idx_notif_rule_id", table_name="notifications")
    op.drop_column("notifications", "why_json")
    op.drop_column("notifications", "rule_id")
    op.drop_column("notifications", "tier")
