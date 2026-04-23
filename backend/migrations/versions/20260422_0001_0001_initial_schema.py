"""Initial schema — all 10 tables + FTS5 search_index virtual table + triggers.

Revision ID: 0001
Revises:
Create Date: 2026-04-22
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "children",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("display_name", sa.String, nullable=False),
        sa.Column("class_level", sa.Integer, nullable=False),
        sa.Column("class_section", sa.String, nullable=True),
        sa.Column("school", sa.String, nullable=False, server_default="Vasant Valley"),
        sa.Column("veracross_id", sa.String, nullable=True, unique=True),
        sa.Column("syllabus_path", sa.String, nullable=True),
        sa.Column("settings", sa.String, nullable=False, server_default="{}"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    op.create_table(
        "veracross_items",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("child_id", sa.Integer, sa.ForeignKey("children.id"), nullable=False),
        sa.Column("kind", sa.String, nullable=False),
        sa.Column("external_id", sa.String, nullable=False),
        sa.Column("subject", sa.String, nullable=True),
        sa.Column("title", sa.String, nullable=True),
        sa.Column("due_or_date", sa.String, nullable=True),
        sa.Column("raw_json", sa.String, nullable=False),
        sa.Column("normalized_json", sa.String, nullable=True),
        sa.Column("status", sa.String, nullable=True),
        sa.Column("seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "first_seen_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "last_seen_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("child_id", "kind", "external_id", name="uq_vc_items_child_kind_extid"),
    )
    op.create_index(
        "idx_vc_items_child_kind_date",
        "veracross_items",
        ["child_id", "kind", "due_or_date"],
    )
    op.create_index("idx_vc_items_status", "veracross_items", ["status"])

    op.create_table(
        "events",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("kind", sa.String, nullable=False),
        sa.Column("child_id", sa.Integer, sa.ForeignKey("children.id"), nullable=True),
        sa.Column("subject", sa.String, nullable=True),
        sa.Column(
            "related_item_id", sa.Integer, sa.ForeignKey("veracross_items.id"), nullable=True
        ),
        sa.Column("payload_json", sa.String, nullable=False),
        sa.Column("notability", sa.Float, nullable=False),
        sa.Column("dedup_key", sa.String, nullable=False, unique=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("idx_events_child_time", "events", ["child_id", "created_at"])

    op.create_table(
        "notifications",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("event_id", sa.Integer, sa.ForeignKey("events.id"), nullable=False),
        sa.Column("channel", sa.String, nullable=False),
        sa.Column("status", sa.String, nullable=False),
        sa.Column("attempted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error", sa.String, nullable=True),
        sa.Column("message_preview", sa.String, nullable=True),
    )
    op.create_index("idx_notif_event", "notifications", ["event_id"])
    op.create_index("idx_notif_status", "notifications", ["status"])

    op.create_table(
        "parent_notes",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("child_id", sa.Integer, sa.ForeignKey("children.id"), nullable=True),
        sa.Column("note", sa.String, nullable=False),
        sa.Column("tags", sa.String, nullable=True),
        sa.Column(
            "note_date", sa.Date, nullable=False, server_default=sa.func.current_date()
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    op.create_table(
        "summaries",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("child_id", sa.Integer, sa.ForeignKey("children.id"), nullable=True),
        sa.Column("kind", sa.String, nullable=False),
        sa.Column("period_start", sa.String, nullable=False),
        sa.Column("period_end", sa.String, nullable=False),
        sa.Column("content_md", sa.String, nullable=False),
        sa.Column("stats_json", sa.String, nullable=False),
        sa.Column("model_used", sa.String, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint(
            "child_id", "kind", "period_start", name="uq_summaries_child_kind_period"
        ),
    )

    op.create_table(
        "llm_calls",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("purpose", sa.String, nullable=False),
        sa.Column("model", sa.String, nullable=False),
        sa.Column("input_tokens", sa.Integer, nullable=True),
        sa.Column("output_tokens", sa.Integer, nullable=True),
        sa.Column("cost_inr", sa.Float, nullable=True),
        sa.Column("input_hash", sa.String, nullable=True),
        sa.Column("success", sa.Integer, nullable=False),
        sa.Column("error", sa.String, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    op.create_table(
        "sync_runs",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("trigger", sa.String, nullable=False),
        sa.Column("status", sa.String, nullable=False),
        sa.Column("items_new", sa.Integer, server_default="0"),
        sa.Column("items_updated", sa.Integer, server_default="0"),
        sa.Column("events_produced", sa.Integer, server_default="0"),
        sa.Column("notifications_fired", sa.Integer, server_default="0"),
        sa.Column("error", sa.String, nullable=True),
        sa.Column("warnings", sa.String, nullable=True),
    )

    op.create_table(
        "mcp_tool_calls",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("tool", sa.String, nullable=False),
        sa.Column("arguments_json", sa.String, nullable=False),
        sa.Column("client_id", sa.String, nullable=True),
        sa.Column("result_preview", sa.String, nullable=True),
        sa.Column("row_count", sa.Integer, nullable=True),
        sa.Column("error", sa.String, nullable=True),
        sa.Column("duration_ms", sa.Integer, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("idx_mcp_tool_calls_tool_time", "mcp_tool_calls", ["tool", "created_at"])

    op.create_table(
        "channel_config",
        sa.Column("id", sa.Integer, primary_key=True, server_default="1"),
        sa.Column("config_json", sa.String, nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    # FTS5 virtual table for the `ask` tool. Porter stemming + unicode.
    op.execute(
        """
        CREATE VIRTUAL TABLE search_index USING fts5(
            kind,
            child_id UNINDEXED,
            subject,
            title,
            body,
            external_id UNINDEXED,
            created_at UNINDEXED,
            tokenize = "porter unicode61"
        );
        """
    )

    # Keep search_index in sync with veracross_items for text-bearing kinds.
    op.execute(
        """
        CREATE TRIGGER vc_items_ai AFTER INSERT ON veracross_items
        WHEN NEW.kind IN ('assignment','comment','message','school_message','article')
        BEGIN
            INSERT INTO search_index(kind, child_id, subject, title, body, external_id, created_at)
            VALUES (NEW.kind, NEW.child_id, NEW.subject, NEW.title,
                    COALESCE(json_extract(NEW.normalized_json, '$.body'), NEW.title, ''),
                    NEW.external_id, NEW.first_seen_at);
        END;
        """
    )
    op.execute(
        """
        CREATE TRIGGER vc_items_ad AFTER DELETE ON veracross_items
        WHEN OLD.kind IN ('assignment','comment','message','school_message','article')
        BEGIN
            DELETE FROM search_index
            WHERE kind = OLD.kind AND external_id = OLD.external_id;
        END;
        """
    )
    op.execute(
        """
        CREATE TRIGGER vc_items_au AFTER UPDATE ON veracross_items
        WHEN NEW.kind IN ('assignment','comment','message','school_message','article')
        BEGIN
            DELETE FROM search_index
            WHERE kind = OLD.kind AND external_id = OLD.external_id;
            INSERT INTO search_index(kind, child_id, subject, title, body, external_id, created_at)
            VALUES (NEW.kind, NEW.child_id, NEW.subject, NEW.title,
                    COALESCE(json_extract(NEW.normalized_json, '$.body'), NEW.title, ''),
                    NEW.external_id, NEW.first_seen_at);
        END;
        """
    )

    # Index parent_notes in the same virtual table.
    op.execute(
        """
        CREATE TRIGGER parent_notes_ai AFTER INSERT ON parent_notes BEGIN
            INSERT INTO search_index(kind, child_id, subject, title, body, external_id, created_at)
            VALUES ('note', NEW.child_id, NEW.tags, NULL, NEW.note, CAST(NEW.id AS TEXT), NEW.created_at);
        END;
        """
    )
    op.execute(
        """
        CREATE TRIGGER parent_notes_ad AFTER DELETE ON parent_notes BEGIN
            DELETE FROM search_index WHERE kind='note' AND external_id = CAST(OLD.id AS TEXT);
        END;
        """
    )
    op.execute(
        """
        CREATE TRIGGER parent_notes_au AFTER UPDATE ON parent_notes BEGIN
            DELETE FROM search_index WHERE kind='note' AND external_id = CAST(OLD.id AS TEXT);
            INSERT INTO search_index(kind, child_id, subject, title, body, external_id, created_at)
            VALUES ('note', NEW.child_id, NEW.tags, NULL, NEW.note, CAST(NEW.id AS TEXT), NEW.created_at);
        END;
        """
    )


def downgrade() -> None:
    for trg in (
        "parent_notes_au",
        "parent_notes_ad",
        "parent_notes_ai",
        "vc_items_au",
        "vc_items_ad",
        "vc_items_ai",
    ):
        op.execute(f"DROP TRIGGER IF EXISTS {trg};")
    op.execute("DROP TABLE IF EXISTS search_index;")

    for tbl in (
        "channel_config",
        "mcp_tool_calls",
        "sync_runs",
        "llm_calls",
        "summaries",
        "parent_notes",
        "notifications",
        "events",
        "veracross_items",
        "children",
    ):
        op.drop_table(tbl)
