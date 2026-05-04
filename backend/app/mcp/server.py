"""MCP server exposing the parent-cockpit data to Dispatch, OpenClaw, Claude Desktop, etc.

Registers tools once; can be launched either as stdio (via `schoolwork-mcp`) or mounted
into the FastAPI app at /mcp (streamable-http + SSE). Every tool call is logged to
`mcp_tool_calls` for audit.
"""

from __future__ import annotations

import asyncio
import json
import time
from datetime import datetime, timedelta, timezone
from typing import Any

from mcp.server.fastmcp import Context, FastMCP
from sqlalchemy import insert

from ..config import get_settings
from ..db import get_async_session
from ..models import MCPToolCall
from ..services import queries as Q

settings = get_settings()

server = FastMCP(
    name="parent-cockpit",
    instructions=(
        "Parent-facing tracker for Vasant Valley School's Veracross portal "
        "plus Ei Mindspark, parent-uploaded library files, kid events, "
        "syllabus state, and an audit-logged action layer.\n\n"
        "Start with list_children. Then pick a tool by domain:\n"
        "  • Backlog: get_overdue / get_due_today / get_upcoming / list_assignments\n"
        "  • Today's surface: get_today / get_daily_brief\n"
        "  • Cross-cutting questions: ask (FTS5 over comments/messages/notes/articles)\n"
        "  • Grades: get_grades / get_grade_trends / annotate_grade_trends / get_anomalies / explain_grade_anomaly\n"
        "  • Subject mastery: get_topic_state / get_topic_detail / get_shaky_topics / get_excellence_status\n"
        "  • Patterns: get_patterns / get_homework_load / get_sentiment_trend / get_submission_heatmap\n"
        "  • Briefs: get_sunday_brief / get_ptm_brief (Claude-driven, cached nightly at 02:00 IST)\n"
        "  • Worth-a-chat (parent's PTM list): get_worth_a_chat / set_worth_a_chat\n"
        "  • Assignment state changes: update_assignment / mark_assignment_submitted / set_self_prediction\n"
        "    — call get_assignment_constants first for the parent_status enum + tag vocabulary\n"
        "  • Self-prediction calibration: get_self_prediction_calibration\n"
        "  • Files (list): list_attachments / list_spellbee_lists / list_resources / list_library / list_portfolio\n"
        "  • Files (read content): read_attachment / read_spellbee_file / read_resource_file / read_library_file / read_portfolio_file — capped at 5 MB; text returns UTF-8, binary returns base64\n"
        "  • Files (path): resolve_*_path (for local clients with disk access)\n"
        "  • Events (camps, auditions, exams, holidays): list_events / upsert_event / delete_event / extract_events_from_messages\n"
        "  • Library uploads: list_library / reclassify_library_file / delete_library_file\n"
        "  • Mindspark: get_mindspark_progress / trigger_mindspark_sync\n"
        "  • School messages: get_messages / get_school_messages_grouped / summarize_school_message_group\n"
        "  • Notifications: get_notifications / replay_notifications / list_notification_snoozes / add_notification_snooze\n"
        "  • Sync observability: get_sync_runs / get_sync_run_log / get_concurrency_check / trigger_sync\n"
        "  • Channel config: get_channel_config / update_channel_config / test_channel\n"
        "  • Syllabus: get_syllabus / set_syllabus_cycle_override / set_syllabus_topic_status / trigger_syllabus_check\n"
        "  • Audit: get_assignment_history / get_mcp_activity\n\n"
        "Numbers and dates are authoritative; do not invent data not returned by a tool. "
        "Every tool call is logged to mcp_tool_calls."
    ),
)


async def _audit(
    tool: str,
    arguments: dict[str, Any],
    result: Any,
    error: str | None,
    started: float,
    client_id: str | None,
) -> None:
    try:
        preview = json.dumps(result, default=str)[:300] if result is not None else None
        row_count = len(result) if isinstance(result, list) else None
        async with get_async_session() as session:
            await session.execute(
                insert(MCPToolCall).values(
                    tool=tool,
                    arguments_json=json.dumps(arguments, default=str),
                    client_id=client_id,
                    result_preview=preview,
                    row_count=row_count,
                    error=error,
                    duration_ms=int((time.monotonic() - started) * 1000),
                )
            )
            await session.commit()
    except Exception:
        # Auditing must never break a tool call.
        pass


def _client_id(ctx: Context | None) -> str | None:
    if ctx is None:
        return None
    try:
        info = ctx.session.client_params.clientInfo  # type: ignore[attr-defined]
        return f"{info.name}/{info.version}"
    except Exception:
        return None


@server.tool()
async def list_children(ctx: Context | None = None) -> list[dict[str, Any]]:
    """Enumerate the children tracked by the cockpit (id, name, class)."""
    started = time.monotonic()
    err: str | None = None
    result: list[dict[str, Any]] = []
    try:
        async with get_async_session() as session:
            result = await Q.list_children(session)
        return result
    except Exception as e:
        err = repr(e)
        raise
    finally:
        await _audit("list_children", {}, result, err, started, _client_id(ctx))


@server.tool()
async def get_overdue(
    child_id: int | None = None, ctx: Context | None = None
) -> list[dict[str, Any]]:
    """List overdue assignments. If child_id is omitted, returns across both kids."""
    started = time.monotonic()
    err: str | None = None
    result: list[dict[str, Any]] = []
    try:
        async with get_async_session() as session:
            result = await Q.get_overdue(session, child_id=child_id)
        return result
    except Exception as e:
        err = repr(e)
        raise
    finally:
        await _audit(
            "get_overdue", {"child_id": child_id}, result, err, started, _client_id(ctx)
        )


@server.tool()
async def get_due_today(
    child_id: int | None = None, ctx: Context | None = None
) -> list[dict[str, Any]]:
    """List assignments due today (IST)."""
    started = time.monotonic()
    err: str | None = None
    result: list[dict[str, Any]] = []
    try:
        async with get_async_session() as session:
            result = await Q.get_due_today(session, child_id=child_id)
        return result
    except Exception as e:
        err = repr(e)
        raise
    finally:
        await _audit(
            "get_due_today", {"child_id": child_id}, result, err, started, _client_id(ctx)
        )


@server.tool()
async def get_upcoming(
    child_id: int | None = None, days: int = 14, ctx: Context | None = None
) -> list[dict[str, Any]]:
    """List upcoming assignments due in the next N days (default 14)."""
    started = time.monotonic()
    err: str | None = None
    result: list[dict[str, Any]] = []
    try:
        async with get_async_session() as session:
            result = await Q.get_upcoming(session, child_id=child_id, days=days)
        return result
    except Exception as e:
        err = repr(e)
        raise
    finally:
        await _audit(
            "get_upcoming",
            {"child_id": child_id, "days": days},
            result,
            err,
            started,
            _client_id(ctx),
        )


@server.tool()
async def get_messages(
    since_days: int = 7,
    unread_only: bool = False,
    ctx: Context | None = None,
) -> list[dict[str, Any]]:
    """List recent school messages/announcements (last N days)."""
    started = time.monotonic()
    err: str | None = None
    result: list[dict[str, Any]] = []
    try:
        since = datetime.now(tz=timezone.utc) - timedelta(days=since_days)
        async with get_async_session() as session:
            result = await Q.get_messages(session, since=since, unread_only=unread_only)
        return result
    except Exception as e:
        err = repr(e)
        raise
    finally:
        await _audit(
            "get_messages",
            {"since_days": since_days, "unread_only": unread_only},
            result,
            err,
            started,
            _client_id(ctx),
        )


@server.tool()
async def get_today(ctx: Context | None = None) -> dict[str, Any]:
    """Get the full Today view — the same data the 4pm digest is rendered from."""
    started = time.monotonic()
    err: str | None = None
    result: dict[str, Any] = {}
    try:
        async with get_async_session() as session:
            result = await Q.get_today(session)
        return result
    except Exception as e:
        err = repr(e)
        raise
    finally:
        await _audit("get_today", {}, result, err, started, _client_id(ctx))


@server.tool()
async def get_notifications(
    since_days: int = 7,
    kinds: list[str] | None = None,
    child_id: int | None = None,
    limit: int = 100,
    ctx: Context | None = None,
) -> list[dict[str, Any]]:
    """List recent events and their per-channel delivery status (fired or suppressed)."""
    started = time.monotonic()
    err: str | None = None
    result: list[dict[str, Any]] = []
    try:
        since = datetime.now(tz=timezone.utc) - timedelta(days=since_days)
        kinds_tuple = tuple(kinds) if kinds else None
        async with get_async_session() as session:
            result = await Q.get_events(
                session, since=since, kinds=kinds_tuple, child_id=child_id, limit=limit
            )
        return result
    except Exception as e:
        err = repr(e)
        raise
    finally:
        await _audit(
            "get_notifications",
            {
                "since_days": since_days,
                "kinds": kinds,
                "child_id": child_id,
                "limit": limit,
            },
            result,
            err,
            started,
            _client_id(ctx),
        )


@server.tool()
async def get_digest(
    date_iso: str | None = None, ctx: Context | None = None
) -> dict[str, Any] | None:
    """Get the pre-rendered digest for a specific date (default: today).

    Returns None if no digest has been generated for that date yet — in which case
    the caller should use get_today for a live snapshot.
    """
    started = time.monotonic()
    err: str | None = None
    result: dict[str, Any] | None = None
    try:
        d = None
        if date_iso:
            d = datetime.fromisoformat(date_iso).date()
        async with get_async_session() as session:
            result = await Q.get_digest_summary(session, d=d)
        return result
    except Exception as e:
        err = repr(e)
        raise
    finally:
        await _audit(
            "get_digest", {"date_iso": date_iso}, result, err, started, _client_id(ctx)
        )


@server.tool()
async def ask(
    query: str,
    child_id: int | None = None,
    kinds: list[str] | None = None,
    since_days: int | None = None,
    limit: int = 10,
    ctx: Context | None = None,
) -> dict[str, Any]:
    """Free-form search across assignments, teacher comments, school messages, articles,
    and parent notes. Returns ranked passages; the caller synthesizes the answer.

    Example queries: "cricket camp fee", "Tejas fractions worksheet", "handwriting".
    """
    started = time.monotonic()
    err: str | None = None
    result: dict[str, Any] = {"query": query, "results": []}
    try:
        since = (
            datetime.now(tz=timezone.utc) - timedelta(days=since_days)
            if since_days
            else None
        )
        kinds_tuple = tuple(kinds) if kinds else None
        async with get_async_session() as session:
            rows = await Q.search(
                session,
                query=query,
                child_id=child_id,
                kinds=kinds_tuple,
                since=since,
                limit=limit,
            )
        result = {"query": query, "results": rows}
        return result
    except Exception as e:
        err = repr(e)
        raise
    finally:
        await _audit(
            "ask",
            {
                "query": query,
                "child_id": child_id,
                "kinds": kinds,
                "since_days": since_days,
                "limit": limit,
            },
            result,
            err,
            started,
            _client_id(ctx),
        )


@server.tool()
async def add_note(
    text: str,
    child_id: int | None = None,
    tags: str | None = None,
    ctx: Context | None = None,
) -> dict[str, Any]:
    """Append a parent note (free text). Optionally scoped to a child or tagged."""
    started = time.monotonic()
    err: str | None = None
    result: dict[str, Any] = {}
    try:
        async with get_async_session() as session:
            result = await Q.add_parent_note(
                session, text=text, child_id=child_id, tags=tags
            )
        return result
    except Exception as e:
        err = repr(e)
        raise
    finally:
        await _audit(
            "add_note",
            {"text": text[:200], "child_id": child_id, "tags": tags},
            result,
            err,
            started,
            _client_id(ctx),
        )


@server.tool()
async def get_grades(
    child_id: int, subject: str | None = None, ctx: Context | None = None
) -> list[dict[str, Any]]:
    """Recent grades for a child. Optionally filter by subject name."""
    started = time.monotonic()
    err: str | None = None
    result: list[dict[str, Any]] = []
    try:
        async with get_async_session() as session:
            result = await Q.get_grades(session, child_id=child_id, subject=subject)
        return result
    except Exception as e:
        err = repr(e)
        raise
    finally:
        await _audit(
            "get_grades", {"child_id": child_id, "subject": subject},
            result, err, started, _client_id(ctx),
        )


@server.tool()
async def get_grade_trends(
    child_id: int, ctx: Context | None = None
) -> list[dict[str, Any]]:
    """Per-subject grade trend: sparkline, arrow, latest/avg/min/max, last 5 grades."""
    started = time.monotonic()
    err: str | None = None
    result: list[dict[str, Any]] = []
    try:
        async with get_async_session() as session:
            result = await Q.get_grade_trends(session, child_id=child_id)
        return result
    except Exception as e:
        err = repr(e)
        raise
    finally:
        await _audit(
            "get_grade_trends", {"child_id": child_id},
            result, err, started, _client_id(ctx),
        )


@server.tool()
async def get_channel_config(ctx: Context | None = None) -> dict[str, Any]:
    """Return the current notification channel policy (thresholds, mute lists, rate limits)."""
    started = time.monotonic()
    err: str | None = None
    result: dict[str, Any] = {}
    try:
        from ..notability.dispatcher import load_config
        async with get_async_session() as s:
            result = await load_config(s)
        return result
    except Exception as e:
        err = repr(e)
        raise
    finally:
        await _audit("get_channel_config", {}, result, err, started, _client_id(ctx))


@server.tool()
async def get_comments(
    child_id: int | None = None, limit: int = 50, ctx: Context | None = None
) -> list[dict[str, Any]]:
    """Teacher comment items across one or all children (most recent first)."""
    started = time.monotonic()
    err: str | None = None
    result: list[dict[str, Any]] = []
    try:
        async with get_async_session() as session:
            result = await Q.get_comments(session, child_id=child_id, limit=limit)
        return result
    except Exception as e:
        err = repr(e)
        raise
    finally:
        await _audit(
            "get_comments", {"child_id": child_id, "limit": limit},
            result, err, started, _client_id(ctx),
        )


@server.tool()
async def get_notes(
    child_id: int | None = None, limit: int = 50, ctx: Context | None = None
) -> list[dict[str, Any]]:
    """Parent-authored notes across one or all children (most recent first)."""
    started = time.monotonic()
    err: str | None = None
    result: list[dict[str, Any]] = []
    try:
        async with get_async_session() as session:
            result = await Q.get_notes(session, child_id=child_id, limit=limit)
        return result
    except Exception as e:
        err = repr(e)
        raise
    finally:
        await _audit(
            "get_notes", {"child_id": child_id, "limit": limit},
            result, err, started, _client_id(ctx),
        )


@server.tool()
async def get_summaries(
    kind: str | None = None, limit: int = 30, ctx: Context | None = None
) -> list[dict[str, Any]]:
    """Past digest summaries (kind = digest_4pm|weekly|cycle_review). Most recent first."""
    started = time.monotonic()
    err: str | None = None
    result: list[dict[str, Any]] = []
    try:
        async with get_async_session() as session:
            result = await Q.get_summaries(session, kind=kind, limit=limit)
        return result
    except Exception as e:
        err = repr(e)
        raise
    finally:
        await _audit(
            "get_summaries", {"kind": kind, "limit": limit},
            result, err, started, _client_id(ctx),
        )


@server.tool()
async def get_overdue_trend(
    child_id: int | None = None, days: int = 14, ctx: Context | None = None
) -> list[dict[str, Any]]:
    """14-day (configurable) overdue-backlog trend — [{date, count}] oldest → newest."""
    started = time.monotonic()
    err: str | None = None
    result: list[dict[str, Any]] = []
    try:
        async with get_async_session() as session:
            result = await Q.get_overdue_trend(session, child_id=child_id, days=days)
        return result
    except Exception as e:
        err = repr(e)
        raise
    finally:
        await _audit(
            "get_overdue_trend", {"child_id": child_id, "days": days},
            result, err, started, _client_id(ctx),
        )


@server.tool()
async def annotate_grade_trends(
    child_id: int, ctx: Context | None = None
) -> list[dict[str, Any]]:
    """Grade-trend rows with an LLM-written one-sentence annotation that references
    the current learning cycle. Falls back to numeric-only if no LLM configured."""
    started = time.monotonic()
    err: str | None = None
    result: list[dict[str, Any]] = []
    try:
        from ..services.annotations import annotate_grade_trends as _ann
        async with get_async_session() as session:
            result = await _ann(session, child_id)
        return result
    except Exception as e:
        err = repr(e)
        raise
    finally:
        await _audit(
            "annotate_grade_trends", {"child_id": child_id},
            result, err, started, _client_id(ctx),
        )


@server.tool()
async def replay_notifications(
    since_days: int = 7, child_id: int | None = None, ctx: Context | None = None
) -> dict[str, Any]:
    """Counterfactual replay of recent events under the *current* channel policy.
    Returns per-event (replay_status, reason) plus a summary of how many would
    change. No messages are re-sent."""
    started = time.monotonic()
    err: str | None = None
    result: dict[str, Any] = {}
    try:
        from ..services.replay import replay_notifications as _replay
        async with get_async_session() as session:
            result = await _replay(session, since_days=since_days, child_id=child_id)
        return result
    except Exception as e:
        err = repr(e)
        raise
    finally:
        await _audit(
            "replay_notifications", {"since_days": since_days, "child_id": child_id},
            result, err, started, _client_id(ctx),
        )


@server.tool()
async def get_syllabus(
    class_level: int, ctx: Context | None = None
) -> dict[str, Any]:
    """Syllabus for a class level (4 or 6) with parent-side overrides merged in."""
    started = time.monotonic()
    err: str | None = None
    result: dict[str, Any] = {}
    try:
        from ..services.syllabus import merged_syllabus
        async with get_async_session() as session:
            result = await merged_syllabus(session, class_level)
        return result
    except Exception as e:
        err = repr(e)
        raise
    finally:
        await _audit(
            "get_syllabus", {"class_level": class_level},
            result, err, started, _client_id(ctx),
        )


@server.tool()
async def set_syllabus_cycle_override(
    class_level: int,
    cycle_name: str,
    start: str | None = None,
    end: str | None = None,
    note: str | None = None,
    ctx: Context | None = None,
) -> dict[str, Any]:
    """Shift a learning-cycle's date boundaries (e.g. LC2 started a week late).
    Pass null start+end+note to clear the override."""
    started = time.monotonic()
    err: str | None = None
    result: dict[str, Any] = {}
    try:
        from ..services.syllabus import upsert_cycle_override
        async with get_async_session() as session:
            result = await upsert_cycle_override(
                session, class_level=class_level, cycle_name=cycle_name,
                start=start, end=end, note=note,
            )
        return result
    except Exception as e:
        err = repr(e)
        raise
    finally:
        await _audit(
            "set_syllabus_cycle_override",
            {"class_level": class_level, "cycle_name": cycle_name, "start": start, "end": end},
            result, err, started, _client_id(ctx),
        )


@server.tool()
async def mark_assignment_submitted(
    item_id: int, submitted: bool = True, ctx: Context | None = None
) -> dict[str, Any]:
    """Parent-side override when the teacher hasn't updated the portal yet. Pass
    `submitted=False` to clear the override. Accepts the veracross_items.id integer."""
    started = time.monotonic()
    err: str | None = None
    result: dict[str, Any] = {}
    try:
        async with get_async_session() as session:
            result = await Q.mark_assignment_submitted(session, item_id, submitted=submitted)
        return result
    except Exception as e:
        err = repr(e)
        raise
    finally:
        await _audit(
            "mark_assignment_submitted",
            {"item_id": item_id, "submitted": submitted},
            result, err, started, _client_id(ctx),
        )


@server.tool()
async def update_channel_config(
    config: dict[str, Any], ctx: Context | None = None
) -> dict[str, Any]:
    """Overwrite the channel policy. Provide the full config object (same shape as
    get_channel_config returns). Stored in the channel_config singleton row."""
    started = time.monotonic()
    err: str | None = None
    result: dict[str, Any] = {"status": "ok"}
    try:
        from ..notability.dispatcher import save_config
        async with get_async_session() as s:
            await save_config(s, config)
        return result
    except Exception as e:
        err = repr(e)
        raise
    finally:
        await _audit("update_channel_config", {"keys": list(config.keys())}, result, err, started, _client_id(ctx))


@server.tool()
async def test_channel(
    channel: str, message: str = "Hello from Parent Cockpit", ctx: Context | None = None
) -> dict[str, Any]:
    """Send a test message through one channel (telegram|email|inapp)."""
    started = time.monotonic()
    err: str | None = None
    result: dict[str, Any] = {}
    try:
        from ..channels.email import EmailChannel
        from ..channels.inapp import InAppChannel
        from ..channels.telegram import TelegramChannel
        channels = {
            "telegram": TelegramChannel,
            "email": EmailChannel,
            "inapp": InAppChannel,
        }
        cls = channels.get(channel)
        if cls is None:
            raise ValueError(f"unknown channel: {channel}")
        r = await cls().send_test(message)
        result = {"channel": r.channel, "status": r.status, "error": r.error}
        return result
    except Exception as e:
        err = repr(e)
        raise
    finally:
        await _audit(
            "test_channel", {"channel": channel, "message": message[:80]},
            result, err, started, _client_id(ctx),
        )


@server.tool()
async def send_digest(
    kind: str = "digest_4pm", ctx: Context | None = None
) -> dict[str, Any]:
    """Build and dispatch a digest across all configured channels. Kind: 'digest_4pm' | 'weekly'."""
    started = time.monotonic()
    err: str | None = None
    result: dict[str, Any] = {}
    try:
        from ..jobs.digest_job import run_daily_digest, run_weekly_digest
        if kind == "digest_4pm":
            await run_daily_digest()
        elif kind == "weekly":
            await run_weekly_digest()
        else:
            raise ValueError(f"unknown digest kind: {kind}")
        result = {"status": "ok", "kind": kind}
        return result
    except Exception as e:
        err = repr(e)
        raise
    finally:
        await _audit("send_digest", {"kind": kind}, result, err, started, _client_id(ctx))


@server.tool()
async def get_digest_preview(ctx: Context | None = None) -> dict[str, Any]:
    """Build (but don't dispatch) a digest from the current DB state. Returns
    rendered text + HTML + telegram markdown + the structured data."""
    started = time.monotonic()
    err: str | None = None
    result: dict[str, Any] = {}
    try:
        from ..services.briefing import generate_and_store_digest
        from ..services.render import render_for_digest
        data = await generate_and_store_digest(kind="digest_preview", llm=False)
        result = render_for_digest(data)
        return result
    except Exception as e:
        err = repr(e)
        raise
    finally:
        await _audit(
            "get_digest_preview", {}, {"text_len": len(result.get("text",""))},
            err, started, _client_id(ctx),
        )


@server.tool()
async def trigger_sync(
    wait: bool = False,
    include_grades: bool = False,
    grading_periods: list[int] | None = None,
    ctx: Context | None = None,
) -> dict[str, Any]:
    """Kick off a Veracross sync.
    - wait=True blocks and returns the full summary; default False = queued.
    - include_grades=True adds a grade-report scan (expensive). Default False for
      hourly syncs; enable weekly or on-demand to refresh grade trends.
    - grading_periods: list of period IDs to fetch (e.g. [13,15,19,21] for all four
      learning cycles). Defaults to the current period from settings.
    """
    started = time.monotonic()
    err: str | None = None
    result: dict[str, Any] = {}
    try:
        from ..scraper.sync import run_sync
        periods_tuple = tuple(grading_periods) if grading_periods else None
        if wait:
            result = await run_sync(
                trigger="mcp-wait",
                include_grades=include_grades,
                grading_periods=periods_tuple,
            )
        else:
            task = asyncio.create_task(
                run_sync(
                    trigger="mcp",
                    include_grades=include_grades,
                    grading_periods=periods_tuple,
                )
            )
            await asyncio.sleep(0)
            result = {
                "status": "queued",
                "note": "sync running in background",
                "task_name": task.get_name(),
                "include_grades": include_grades,
            }
        return result
    except Exception as e:
        err = repr(e)
        raise
    finally:
        await _audit(
            "trigger_sync",
            {"wait": wait, "include_grades": include_grades, "grading_periods": grading_periods},
            result, err, started, _client_id(ctx),
        )


@server.tool()
async def update_assignment(
    item_id: int,
    parent_status: str | None = None,
    priority: int | None = None,
    snooze_until: str | None = None,
    status_notes: str | None = None,
    tags: list[str] | None = None,
    note: str | None = None,
    ctx: Context | None = None,
) -> dict[str, Any]:
    """Partial update of parent-side assignment state. Every changed field is
    logged to assignment_status_history.

    - parent_status: one of in_progress | done_at_home | submitted | needs_help
      | blocked | skipped, or "" / None to clear.
    - priority: 0..3 (stars).
    - snooze_until: ISO date 'YYYY-MM-DD' (or None to clear).
    - status_notes: free text.
    - tags: list of tag strings (replaces existing tags; see
      get_assignment_constants for the fixed vocabulary).
    - note: optional explanation written to the audit log for this change.
    """
    started = time.monotonic()
    err: str | None = None
    result: dict[str, Any] = {}
    try:
        from ..services import assignment_state as ast
        payload: dict[str, Any] = {}
        if parent_status is not None:
            payload["parent_status"] = parent_status
        if priority is not None:
            payload["priority"] = priority
        if snooze_until is not None:
            payload["snooze_until"] = snooze_until
        if status_notes is not None:
            payload["status_notes"] = status_notes
        if tags is not None:
            payload["tags"] = tags
        if note:
            payload["note"] = note
        payload["actor"] = f"mcp:{_client_id(ctx) or 'unknown'}"
        async with get_async_session() as session:
            r = await ast.update_assignment_state(
                session, item_id, payload, actor=payload.get("actor"),
            )
        if r is None:
            raise ValueError(f"assignment {item_id} not found")
        result = r
        return result
    except Exception as e:
        err = repr(e)
        raise
    finally:
        await _audit(
            "update_assignment",
            {"item_id": item_id, "fields": sorted(payload.keys()) if 'payload' in locals() else []},
            result, err, started, _client_id(ctx),
        )


@server.tool()
async def get_assignment_history(
    item_id: int, limit: int = 200, ctx: Context | None = None,
) -> list[dict[str, Any]]:
    """Status-change audit log for one assignment. Each entry has field,
    old_value, new_value, source, actor, note, created_at."""
    started = time.monotonic()
    err: str | None = None
    result: list[dict[str, Any]] = []
    try:
        from ..services import assignment_state as ast
        async with get_async_session() as session:
            result = await ast.get_history(session, item_id, limit=limit)
        return result
    except Exception as e:
        err = repr(e)
        raise
    finally:
        await _audit(
            "get_assignment_history",
            {"item_id": item_id, "limit": limit},
            result, err, started, _client_id(ctx),
        )


@server.tool()
async def get_assignment_constants(ctx: Context | None = None) -> dict[str, Any]:
    """The fixed vocabulary used by update_assignment — parent-status enum and
    tag list. Call this before building an update_assignment payload."""
    started = time.monotonic()
    err: str | None = None
    result: dict[str, Any] = {}
    try:
        from ..services import assignment_state as ast
        result = {
            "parent_statuses": list(ast.PARENT_STATUSES),
            "fixed_tags": list(ast.FIXED_TAGS),
        }
        return result
    except Exception as e:
        err = repr(e)
        raise
    finally:
        await _audit("get_assignment_constants", {}, result, err, started, _client_id(ctx))


@server.tool()
async def list_attachments(
    child_id: int | None = None,
    source_kind: str | None = None,
    limit: int = 200,
    ctx: Context | None = None,
) -> list[dict[str, Any]]:
    """Files downloaded from Veracross (PDFs, images, docs). Each row includes
    download_url — prefix with the cockpit base URL to fetch bytes via HTTP.
    source_kind filters by originating item kind (assignment | comment | message)."""
    started = time.monotonic()
    err: str | None = None
    result: list[dict[str, Any]] = []
    try:
        async with get_async_session() as session:
            result = await Q.list_attachments(
                session, child_id=child_id, source_kind=source_kind, limit=limit,
            )
        return result
    except Exception as e:
        err = repr(e)
        raise
    finally:
        await _audit(
            "list_attachments",
            {"child_id": child_id, "source_kind": source_kind, "limit": limit},
            result, err, started, _client_id(ctx),
        )


@server.tool()
async def list_spellbee_lists(
    child_id: int, ctx: Context | None = None,
) -> list[dict[str, Any]]:
    """Spelling Bee word lists for one child, stored under
    data/rawdata/<kid_slug>/spellbee/. Each entry has the parsed list number
    (or null) plus a download_url for fetching the file."""
    started = time.monotonic()
    err: str | None = None
    result: list[dict[str, Any]] = []
    try:
        from sqlalchemy import select
        from ..models import Child
        from ..services import spellbee as SB
        async with get_async_session() as session:
            child = (
                await session.execute(select(Child).where(Child.id == child_id))
            ).scalar_one_or_none()
        if child is None:
            raise ValueError(f"child {child_id} not found")
        result = [x.to_dict() for x in SB.list_lists(child)]
        return result
    except Exception as e:
        err = repr(e)
        raise
    finally:
        await _audit("list_spellbee_lists", {"child_id": child_id}, result, err, started, _client_id(ctx))


@server.tool()
async def get_sync_runs(
    limit: int = 20, ctx: Context | None = None,
) -> list[dict[str, Any]]:
    """Recent Veracross sync runs, newest first. Each entry has status, timing,
    item counts, and whether a captured log is available."""
    started = time.monotonic()
    err: str | None = None
    result: list[dict[str, Any]] = []
    try:
        from sqlalchemy import desc, select, func as _func
        from ..models import SyncRun
        async with get_async_session() as session:
            rows = (
                await session.execute(
                    select(
                        SyncRun.id, SyncRun.started_at, SyncRun.ended_at,
                        SyncRun.trigger, SyncRun.status,
                        SyncRun.items_new, SyncRun.items_updated,
                        SyncRun.events_produced, SyncRun.notifications_fired,
                        SyncRun.error,
                        _func.length(SyncRun.log_text).label("log_length"),
                    ).order_by(desc(SyncRun.started_at)).limit(limit)
                )
            ).all()
            result = [
                {
                    "id": r.id,
                    "started_at": r.started_at.isoformat() if r.started_at else None,
                    "ended_at": r.ended_at.isoformat() if r.ended_at else None,
                    "trigger": r.trigger,
                    "status": r.status,
                    "items_new": r.items_new,
                    "items_updated": r.items_updated,
                    "events_produced": r.events_produced,
                    "notifications_fired": r.notifications_fired,
                    "error": r.error,
                    "has_log": bool(r.log_length and r.log_length > 0),
                }
                for r in rows
            ]
        return result
    except Exception as e:
        err = repr(e)
        raise
    finally:
        await _audit("get_sync_runs", {"limit": limit}, result, err, started, _client_id(ctx))


@server.tool()
async def get_sync_run_log(run_id: int, ctx: Context | None = None) -> dict[str, Any]:
    """Captured log text for one sync run. Includes log_capture_healthy flag
    (True iff start + end sentinels are present)."""
    started = time.monotonic()
    err: str | None = None
    result: dict[str, Any] = {}
    try:
        from sqlalchemy import select
        from ..models import SyncRun
        async with get_async_session() as session:
            r = (
                await session.execute(select(SyncRun).where(SyncRun.id == run_id))
            ).scalar_one_or_none()
        if r is None:
            raise ValueError(f"sync run {run_id} not found")
        log_text = r.log_text or ""
        has_start = "=== sync started" in log_text
        has_end = "=== sync ended" in log_text
        is_running = r.status == "running"
        healthy = (is_running and has_start) or (
            not is_running and has_start and has_end
        )
        result = {
            "id": r.id,
            "status": r.status,
            "started_at": r.started_at.isoformat() if r.started_at else None,
            "ended_at": r.ended_at.isoformat() if r.ended_at else None,
            "trigger": r.trigger,
            "error": r.error,
            "log_text": log_text,
            "log_line_count": len(log_text.splitlines()),
            "log_capture_healthy": healthy,
        }
        return result
    except Exception as e:
        err = repr(e)
        raise
    finally:
        await _audit(
            "get_sync_run_log", {"run_id": run_id},
            {"line_count": result.get("log_line_count")}, err, started, _client_id(ctx),
        )


@server.tool()
async def set_syllabus_topic_status(
    class_level: int,
    subject: str,
    topic: str,
    status: str | None,
    note: str | None = None,
    ctx: Context | None = None,
) -> dict[str, Any]:
    """Mark a syllabus topic as covered | skipped | delayed | in_progress (or
    pass status=None to clear). Persists to the per-class syllabus override
    file and shows up in the /child/:id/syllabus UI."""
    started = time.monotonic()
    err: str | None = None
    result: dict[str, Any] = {"status": "ok"}
    try:
        from ..services.syllabus import upsert_topic_status
        async with get_async_session() as session:
            result = await upsert_topic_status(
                session, class_level, subject, topic, status=status, note=note,
            )
        return result
    except Exception as e:
        err = repr(e)
        raise
    finally:
        await _audit(
            "set_syllabus_topic_status",
            {"class_level": class_level, "subject": subject, "topic": topic, "status": status},
            result, err, started, _client_id(ctx),
        )


@server.tool()
async def get_child_detail(child_id: int, ctx: Context | None = None) -> dict[str, Any]:
    """One-shot dashboard for a single child: overdue / due_today / upcoming
    lists, grade_trends, overdue sparkline, current syllabus cycle, and
    counts. Same payload the /child/:id web page hydrates from."""
    started = time.monotonic()
    err: str | None = None
    result: dict[str, Any] = {}
    try:
        async with get_async_session() as session:
            r = await Q.get_child_detail(session, child_id)
        if r is None:
            raise ValueError(f"child {child_id} not found")
        result = r
        return result
    except Exception as e:
        err = repr(e)
        raise
    finally:
        await _audit(
            "get_child_detail", {"child_id": child_id},
            {"keys": sorted(result.keys())}, err, started, _client_id(ctx),
        )


@server.tool()
async def list_assignments(
    child_id: int | None = None,
    subject: str | None = None,
    status: str | None = None,
    limit: int = 200,
    ctx: Context | None = None,
) -> list[dict[str, Any]]:
    """All assignments (not just overdue/due-today/upcoming), with optional
    filters. status matches the portal_status column (e.g. 'done', 'due',
    'missing'). Use this when the caller needs the full history for a
    subject or a free-form query across everything."""
    started = time.monotonic()
    err: str | None = None
    result: list[dict[str, Any]] = []
    try:
        async with get_async_session() as session:
            result = await Q.get_all_assignments(
                session, child_id=child_id, subject=subject, status=status, limit=limit,
            )
        return result
    except Exception as e:
        err = repr(e)
        raise
    finally:
        await _audit(
            "list_assignments",
            {"child_id": child_id, "subject": subject, "status": status, "limit": limit},
            result, err, started, _client_id(ctx),
        )


@server.tool()
async def get_veracross_status(ctx: Context | None = None) -> dict[str, Any]:
    """Snapshot of Veracross scraper health — last sync's outcome, age,
    classified causality, and whether a re-auth is likely required.
    Doesn't hit the portal; reads from sync_run rows."""
    started = time.monotonic()
    err: str | None = None
    result: dict[str, Any] = {}
    try:
        from ..services.sync_health import snapshot
        async with get_async_session() as session:
            result = await snapshot(session)
        return result
    except Exception as e:
        err = repr(e)
        raise
    finally:
        await _audit("get_veracross_status", {}, result, err, started, _client_id(ctx))


@server.tool()
async def check_veracross_auth(ctx: Context | None = None) -> dict[str, Any]:
    """Live probe — loads the persisted session cookie and does one HTTPX
    GET to the Veracross portal to decide if the session is actually
    valid. Cheap (~200ms); much faster than running a full sync. Use before
    suggesting that the parent needs to re-login."""
    started = time.monotonic()
    err: str | None = None
    result: dict[str, Any] = {}
    try:
        from ..services.auth_check import probe
        result = await probe()
        return result
    except Exception as e:
        err = repr(e)
        raise
    finally:
        await _audit("check_veracross_auth", {}, result, err, started, _client_id(ctx))


@server.tool()
async def trigger_syllabus_check(ctx: Context | None = None) -> dict[str, Any]:
    """Kick off the weekly syllabus-vs-portal consistency job. Compares the
    per-class syllabus topic list to what's been scraped and flags gaps."""
    started = time.monotonic()
    err: str | None = None
    result: dict[str, Any] = {}
    try:
        from ..jobs.syllabus_job import check_syllabus_updates
        r = await check_syllabus_updates()
        result = {"status": "ok", **r}
        return result
    except Exception as e:
        err = repr(e)
        raise
    finally:
        await _audit("trigger_syllabus_check", {}, result, err, started, _client_id(ctx))


@server.tool()
async def get_concurrency_check(ctx: Context | None = None) -> dict[str, Any]:
    """How many syncs are currently running. `multiple_running=True` means
    the guard failed somewhere and two concurrent syncs are live — reason
    to investigate."""
    started = time.monotonic()
    err: str | None = None
    result: dict[str, Any] = {}
    try:
        from sqlalchemy import select, desc
        from ..models import SyncRun
        from datetime import datetime, timezone
        async with get_async_session() as session:
            running = (
                await session.execute(
                    select(SyncRun).where(SyncRun.status == "running").order_by(desc(SyncRun.started_at))
                )
            ).scalars().all()
        now = datetime.now(tz=timezone.utc)
        result = {
            "count": len(running),
            "multiple_running": len(running) > 1,
            "runs": [
                {
                    "id": r.id,
                    "started_at": r.started_at.isoformat() if r.started_at else None,
                    "age_sec": int((now - r.started_at).total_seconds()) if r.started_at else None,
                    "trigger": r.trigger,
                }
                for r in running
            ],
        }
        return result
    except Exception as e:
        err = repr(e)
        raise
    finally:
        await _audit("get_concurrency_check", {}, result, err, started, _client_id(ctx))


@server.tool()
async def get_mcp_activity(
    limit: int = 50, ctx: Context | None = None,
) -> list[dict[str, Any]]:
    """Recent MCP tool-call audit entries from the cockpit's own log. Useful
    to see what Claude Desktop / OpenClaw / other clients have been doing."""
    started = time.monotonic()
    err: str | None = None
    result: list[dict[str, Any]] = []
    try:
        from sqlalchemy import desc, select
        from ..models import MCPToolCall
        async with get_async_session() as session:
            rows = (
                await session.execute(
                    select(MCPToolCall).order_by(desc(MCPToolCall.created_at)).limit(limit)
                )
            ).scalars().all()
            result = [
                {
                    "id": r.id,
                    "tool": r.tool,
                    "client_id": r.client_id,
                    "arguments": r.arguments_json,
                    "result_preview": r.result_preview,
                    "row_count": r.row_count,
                    "error": r.error,
                    "duration_ms": r.duration_ms,
                    "created_at": r.created_at.isoformat() if r.created_at else None,
                }
                for r in rows
            ]
        return result
    except Exception as e:
        err = repr(e)
        raise
    finally:
        await _audit("get_mcp_activity", {"limit": limit}, {"rows": len(result)}, err, started, _client_id(ctx))


@server.tool()
async def resolve_attachment_path(
    attachment_id: int, ctx: Context | None = None,
) -> dict[str, Any]:
    """For LOCAL clients — returns the absolute filesystem path of a
    downloaded attachment so Claude Desktop / OpenClaw can read the bytes
    directly (Read tool on the path). Also includes mime_type + filename.
    Guards against path traversal (file must be under data/attachments/)."""
    started = time.monotonic()
    err: str | None = None
    result: dict[str, Any] = {}
    try:
        from ..config import REPO_ROOT
        from ..util import paths as P
        async with get_async_session() as session:
            att = await Q.get_attachment_row(session, attachment_id)
        if att is None:
            raise ValueError(f"attachment {attachment_id} not found")
        path = (REPO_ROOT / att.local_path).resolve()
        try:
            path.relative_to(P.data_root().resolve())
        except ValueError:
            raise ValueError(f"attachment path escapes storage root: {att.local_path}")
        if not path.exists():
            raise ValueError(f"file vanished on disk: {att.local_path}")
        result = {
            "id": att.id,
            "absolute_path": str(path),
            "filename": att.filename,
            "mime_type": att.mime_type,
            "size_bytes": att.size_bytes,
            "sha256": att.sha256,
        }
        return result
    except Exception as e:
        err = repr(e)
        raise
    finally:
        await _audit(
            "resolve_attachment_path", {"attachment_id": attachment_id},
            {"path": result.get("absolute_path")}, err, started, _client_id(ctx),
        )


@server.tool()
async def resolve_spellbee_path(
    child_id: int, filename: str, ctx: Context | None = None,
) -> dict[str, Any]:
    """For LOCAL clients — absolute filesystem path of a Spelling Bee list
    file for a given kid, so Claude Desktop / OpenClaw can read it directly."""
    started = time.monotonic()
    err: str | None = None
    result: dict[str, Any] = {}
    try:
        from sqlalchemy import select
        from ..models import Child
        from ..services import spellbee as SB
        async with get_async_session() as session:
            child = (
                await session.execute(select(Child).where(Child.id == child_id))
            ).scalar_one_or_none()
        if child is None:
            raise ValueError(f"child {child_id} not found")
        path = SB.resolve_file(child, filename)
        if path is None:
            raise ValueError(f"spellbee list {filename!r} not found for child {child_id}")
        result = {
            "filename": path.name,
            "absolute_path": str(path),
            "size_bytes": path.stat().st_size,
            "mime_type": SB._MIME_BY_EXT.get(path.suffix.lower(), "application/octet-stream"),
        }
        return result
    except Exception as e:
        err = repr(e)
        raise
    finally:
        await _audit(
            "resolve_spellbee_path", {"child_id": child_id, "filename": filename},
            {"path": result.get("absolute_path")}, err, started, _client_id(ctx),
        )


@server.tool()
async def list_resources(
    child_id: int | None = None,
    category: str | None = None,
    scope: str | None = None,
    ctx: Context | None = None,
) -> dict[str, Any]:
    """Directory listing of portal-harvested resources under data/rawdata/.

    Returns {schoolwide: {category: [files]}, kids: [{child_id, by_category}]}
    — same shape as the /resources UI page.

    Filters (all optional):
      - child_id : only this kid's per-kid bucket (schoolwide still included)
      - category : only this category (e.g. 'spellbee', 'reading', 'news')
      - scope    : 'schoolwide' or 'kid' — drops the other from the output

    Each file entry carries download_url (serve via /api/resources/file/...)
    plus modified_at + size_bytes so the caller can tell what's recent."""
    started = time.monotonic()
    err: str | None = None
    result: dict[str, Any] = {}
    try:
        from sqlalchemy import select
        from ..models import Child
        from ..services import resources_index as RI
        async with get_async_session() as session:
            q = select(Child).order_by(Child.id)
            if child_id is not None:
                q = q.where(Child.id == child_id)
            children = list((await session.execute(q)).scalars().all())
        full = RI.list_everything(children)
        if scope == "kid":
            full["schoolwide"] = {}
        elif scope == "schoolwide":
            full["kids"] = []
        if category:
            full["schoolwide"] = {
                k: v for k, v in full["schoolwide"].items() if k == category
            }
            for k in full["kids"]:
                k["by_category"] = {
                    kk: vv for kk, vv in k["by_category"].items() if kk == category
                }
        result = full
        return result
    except Exception as e:
        err = repr(e)
        raise
    finally:
        await _audit(
            "list_resources",
            {"child_id": child_id, "category": category, "scope": scope},
            {"schoolwide_cats": list(result.get("schoolwide", {}).keys()),
             "kid_count": len(result.get("kids", []))},
            err, started, _client_id(ctx),
        )


@server.tool()
async def resolve_resource_path(
    scope: str,
    category: str,
    filename: str,
    child_id: int | None = None,
    ctx: Context | None = None,
) -> dict[str, Any]:
    """For LOCAL clients — absolute filesystem path of a resource file so
    Claude Desktop / OpenClaw can read the bytes directly.

    scope must be 'schoolwide' or 'kid'. 'kid' requires child_id.
    Path-traversal guarded: file must resolve under data/rawdata/."""
    started = time.monotonic()
    err: str | None = None
    result: dict[str, Any] = {}
    try:
        from sqlalchemy import select
        from ..models import Child
        from ..services import resources_index as RI
        if scope == "schoolwide":
            path = RI.resolve_schoolwide(category, filename)
        elif scope == "kid":
            if child_id is None:
                raise ValueError("child_id required for scope='kid'")
            async with get_async_session() as session:
                child = (
                    await session.execute(select(Child).where(Child.id == child_id))
                ).scalar_one_or_none()
            if child is None:
                raise ValueError(f"child {child_id} not found")
            path = RI.resolve_kid(child, category, filename)
        else:
            raise ValueError(f"scope must be 'schoolwide' or 'kid', got {scope!r}")
        if path is None:
            raise ValueError(f"resource not found: {scope}/{category}/{filename}")
        st = path.stat()
        result = {
            "absolute_path": str(path),
            "filename": path.name,
            "size_bytes": st.st_size,
            "mime_type": RI._mime(path),
            "scope": scope,
            "category": category,
        }
        return result
    except Exception as e:
        err = repr(e)
        raise
    finally:
        await _audit(
            "resolve_resource_path",
            {"scope": scope, "category": category, "filename": filename, "child_id": child_id},
            {"path": result.get("absolute_path")},
            err, started, _client_id(ctx),
        )


async def _load_child(child_id: int):
    from sqlalchemy import select
    from ..models import Child
    async with get_async_session() as session:
        child = (
            await session.execute(select(Child).where(Child.id == child_id))
        ).scalar_one_or_none()
    if child is None:
        raise ValueError(f"child {child_id} not found")
    return child


@server.tool()
async def get_spellbee_linked_assignments(
    child_id: int | None = None, ctx: Context | None = None,
) -> list[dict[str, Any]]:
    """Every current assignment whose title/body references the Spelling Bee,
    along with the detected 'List N' number (if any) and the matching uploaded
    file (if one exists for that kid). Use this to answer 'what spelling-bee
    work is due + which list does each reference?' in one call."""
    started = time.monotonic()
    err: str | None = None
    result: list[dict[str, Any]] = []
    try:
        from sqlalchemy import select, desc
        import json as _json
        from ..models import Child, VeracrossItem
        from ..services import spellbee as SB
        async with get_async_session() as session:
            stmt = (
                select(VeracrossItem, Child)
                .join(Child, Child.id == VeracrossItem.child_id)
                .where(VeracrossItem.kind == "assignment")
                .order_by(desc(VeracrossItem.first_seen_at))
                .limit(500)
            )
            if child_id is not None:
                stmt = stmt.where(VeracrossItem.child_id == child_id)
            rows = (await session.execute(stmt)).all()
        lists_by_child: dict[int, dict[int, Any]] = {}
        for item, child in rows:
            body = ""
            if item.normalized_json:
                try:
                    body = _json.loads(item.normalized_json).get("body") or ""
                except Exception:
                    body = ""
            texts = (item.title, item.title_en, item.notes_en, body)
            if not SB.is_spellbee_text(*texts):
                continue
            num = SB.detect_list_reference(*texts)
            if child.id not in lists_by_child:
                lists_by_child[child.id] = {
                    l.number: l for l in SB.list_lists(child) if l.number is not None
                }
            match = lists_by_child[child.id].get(num) if num is not None else None
            result.append({
                "id": item.id,
                "child_id": child.id,
                "child_name": child.display_name,
                "subject": item.subject,
                "title": item.title,
                "due_or_date": item.due_or_date,
                "status": item.status,
                "detected_list_number": num,
                "matched_list": match.to_dict() if match else None,
            })
        return result
    except Exception as e:
        err = repr(e)
        raise
    finally:
        await _audit(
            "get_spellbee_linked_assignments",
            {"child_id": child_id}, result, err, started, _client_id(ctx),
        )


@server.tool()
async def delete_spellbee_list(
    child_id: int, filename: str, ctx: Context | None = None,
) -> dict[str, Any]:
    """Remove a Spelling Bee list file from a kid's spellbee/ directory.
    Traversal-guarded. Returns {status: 'deleted'|'not_found', filename}."""
    started = time.monotonic()
    err: str | None = None
    result: dict[str, Any] = {}
    try:
        from ..services import spellbee as SB
        child = await _load_child(child_id)
        ok = SB.delete_file(child, filename)
        result = {"status": "deleted" if ok else "not_found", "filename": filename}
        return result
    except Exception as e:
        err = repr(e)
        raise
    finally:
        await _audit(
            "delete_spellbee_list",
            {"child_id": child_id, "filename": filename},
            result, err, started, _client_id(ctx),
        )


@server.tool()
async def rename_spellbee_list(
    child_id: int, filename: str, new_name: str, ctx: Context | None = None,
) -> dict[str, Any]:
    """Rename a Spelling Bee list file. Use this to fix filenames so the
    list-number parser picks up the ordinal (e.g. rename 'random.pdf' to
    'list-03.pdf'). new_name is sanitized; only allowed extensions accepted."""
    started = time.monotonic()
    err: str | None = None
    result: dict[str, Any] = {}
    try:
        from ..services import spellbee as SB
        child = await _load_child(child_id)
        row = SB.rename_file(child, filename, new_name)
        result = row.to_dict()
        return result
    except Exception as e:
        err = repr(e)
        raise
    finally:
        await _audit(
            "rename_spellbee_list",
            {"child_id": child_id, "filename": filename, "new_name": new_name},
            result, err, started, _client_id(ctx),
        )


@server.tool()
async def get_shaky_topics(
    child_id: int | None = None,
    limit: int = 3,
    ctx: Context | None = None,
) -> list[dict[str, Any]] | dict[str, Any]:
    """Top-N topics per kid that most warrant a parent-kid review
    conversation this week. Capped (default 3) — pushing more triggers
    helicopter-parenting patterns. Each item carries a `reasons` list
    explaining why it surfaced (decaying / weak last score / age).
    Returns by-kid bucket if child_id omitted; just a list otherwise."""
    started = time.monotonic()
    err: str | None = None
    result: Any = None
    try:
        from sqlalchemy import select
        from ..models import Child
        from ..services.shaky_topics import shaky_for_child, shaky_for_all
        async with get_async_session() as session:
            if child_id is None:
                result = await shaky_for_all(session, limit_per_kid=limit)
            else:
                child = (
                    await session.execute(select(Child).where(Child.id == child_id))
                ).scalar_one_or_none()
                if child is None:
                    raise ValueError(f"child {child_id} not found")
                result = await shaky_for_child(session, child, limit=limit)
        return result
    except Exception as e:
        err = repr(e)
        raise
    finally:
        await _audit(
            "get_shaky_topics",
            {"child_id": child_id, "limit": limit},
            None, err, started, _client_id(ctx),
        )


@server.tool()
async def get_excellence_status(
    child_id: int | None = None, ctx: Context | None = None,
) -> list[dict[str, Any]] | dict[str, Any]:
    """Vasant Valley awards 'Excellence' to students who maintain ≥85 %
    overall yearly average for 5 consecutive years. This tool shows
    where the kid currently stands for *this* academic year:
    grades_count, above_85_count, current_year_avg, on_track flag,
    and the 5 most-recent <85 % items for drill-down. Pass child_id
    to limit; otherwise both kids."""
    started = time.monotonic()
    err: str | None = None
    result: Any = None
    try:
        from sqlalchemy import select
        from ..models import Child
        from ..services.excellence import status_for_all, status_for_child
        async with get_async_session() as session:
            if child_id is None:
                result = await status_for_all(session)
            else:
                child = (
                    await session.execute(select(Child).where(Child.id == child_id))
                ).scalar_one_or_none()
                if child is None:
                    raise ValueError(f"child {child_id} not found")
                result = (await status_for_child(session, child)).to_dict()
        return result
    except Exception as e:
        err = repr(e)
        raise
    finally:
        await _audit(
            "get_excellence_status",
            {"child_id": child_id},
            None, err, started, _client_id(ctx),
        )


@server.tool()
async def get_topic_state(
    child_id: int, ctx: Context | None = None,
) -> list[dict[str, Any]]:
    """Per-(subject × topic) mastery state for one kid. State ∈
    {attempted, familiar, proficient, mastered, decaying} based on
    grades + assignments tagged to each syllabus topic via
    `fuzzy_topic_for`. Khan-style heuristics + Cepeda 30-day decay.
    Recomputed weekly by heavy-tier sync; on-demand via
    /api/topic-state/recompute."""
    started = time.monotonic()
    err: str | None = None
    result: list[dict[str, Any]] = []
    try:
        from ..services.topic_state import list_topic_state
        async with get_async_session() as session:
            result = await list_topic_state(session, child_id)
        return result
    except Exception as e:
        err = repr(e)
        raise
    finally:
        await _audit(
            "get_topic_state",
            {"child_id": child_id},
            {"rows": len(result)},
            err, started, _client_id(ctx),
        )


@server.tool()
async def recompute_topic_state(
    child_id: int | None = None, ctx: Context | None = None,
) -> dict[str, Any]:
    """Rebuild topic_state rows from current grades + assignments.
    Idempotent. Pass child_id to limit to one kid; otherwise rebuilds
    all kids."""
    started = time.monotonic()
    err: str | None = None
    result: dict[str, Any] = {}
    try:
        from sqlalchemy import select
        from ..models import Child
        from ..services.topic_state import recompute_for_child, recompute_all
        async with get_async_session() as session:
            if child_id is None:
                result = await recompute_all(session)
            else:
                child = (
                    await session.execute(select(Child).where(Child.id == child_id))
                ).scalar_one_or_none()
                if child is None:
                    raise ValueError(f"child {child_id} not found")
                result = await recompute_for_child(session, child)
        return result
    except Exception as e:
        err = repr(e)
        raise
    finally:
        await _audit(
            "recompute_topic_state",
            {"child_id": child_id},
            result, err, started, _client_id(ctx),
        )


@server.tool()
async def match_grades_to_assignments(
    child_id: int | None = None,
    use_llm_tiebreaker: bool = True,
    ctx: Context | None = None,
) -> dict[str, Any]:
    """Reconcile graded items with the assignments that produced them.
    The school doesn't link them — only soft signals (same kid, similar
    title, plausible date offset) tie a grade like '9/10 on Word Problems
    Quiz' back to the assignment 'Worksheet on Word Problems' from a
    week earlier. Two-pass:
      1. deterministic Jaccard + date proximity (free, fast)
      2. local Ollama LLM tiebreaker only when top two are within margin
    Idempotent — strong existing links are kept. Returns counts +
    per-grade detail."""
    started = time.monotonic()
    err: str | None = None
    result: dict[str, Any] = {}
    try:
        from ..services.grade_match import match_unlinked_grades
        async with get_async_session() as session:
            result = await match_unlinked_grades(
                session, child_id=child_id, use_llm_tiebreaker=use_llm_tiebreaker,
            )
        return result
    except Exception as e:
        err = repr(e)
        raise
    finally:
        await _audit(
            "match_grades_to_assignments",
            {"child_id": child_id, "use_llm_tiebreaker": use_llm_tiebreaker},
            {"counts": result.get("counts")},
            err, started, _client_id(ctx),
        )


@server.tool()
async def get_patterns(
    child_id: int | None = None,
    ctx: Context | None = None,
) -> dict[str, Any] | list[dict[str, Any]]:
    """Read monthly behavioural-pattern flags per kid: lateness,
    repeated_attempt, weekend_cramming. Each row carries supporting
    counts + sample titles in `detail`. Honest framing: signals from
    incomplete data, never verdicts. Pass child_id to limit; otherwise
    both kids."""
    started = time.monotonic()
    err: str | None = None
    result: Any = None
    try:
        from sqlalchemy import select
        from ..models import Child
        from ..services.patterns import list_patterns, list_patterns_all
        async with get_async_session() as session:
            if child_id is None:
                result = await list_patterns_all(session)
            else:
                child = (
                    await session.execute(select(Child).where(Child.id == child_id))
                ).scalar_one_or_none()
                if child is None:
                    raise ValueError(f"child {child_id} not found")
                result = await list_patterns(session, child_id)
        return result
    except Exception as e:
        err = repr(e)
        raise
    finally:
        await _audit(
            "get_patterns",
            {"child_id": child_id},
            None, err, started, _client_id(ctx),
        )


@server.tool()
async def recompute_patterns(
    child_id: int | None = None,
    months: int = 6,
    ctx: Context | None = None,
) -> dict[str, Any]:
    """Rebuild pattern_state for the last `months` calendar months
    (default 6). Idempotent — same month is overwritten, never appended.
    Heavy-tier sync runs this nightly; this tool is for on-demand
    refresh after a data import."""
    started = time.monotonic()
    err: str | None = None
    result: dict[str, Any] = {}
    try:
        from sqlalchemy import select
        from ..models import Child
        from ..services.patterns import compute_all, compute_for_child
        async with get_async_session() as session:
            if child_id is None:
                result = await compute_all(session, months=months)
            else:
                child = (
                    await session.execute(select(Child).where(Child.id == child_id))
                ).scalar_one_or_none()
                if child is None:
                    raise ValueError(f"child {child_id} not found")
                rows = await compute_for_child(session, child, months=months)
                result = {"child_id": child_id, "rows": len(rows), "months": months}
        return result
    except Exception as e:
        err = repr(e)
        raise
    finally:
        await _audit(
            "recompute_patterns",
            {"child_id": child_id, "months": months},
            result, err, started, _client_id(ctx),
        )


@server.tool()
async def get_homework_load(
    child_id: int | None = None,
    weeks: int = 8,
    extra_minutes_per_item: int | None = None,
    ctx: Context | None = None,
) -> dict[str, Any] | list[dict[str, Any]]:
    """Per-week homework load. Bucketed by date the assignment was given
    (date_assigned with fallback to due-date). The cockpit can't measure
    real time-on-task — this is an estimate (assignment count × per-class
    minutes-per-item). Defaults: 20/25/35/45 min for Class I-II /
    III-V / VI-VIII / IX+. The earlier CBSE Circular 52/2020 policy
    cap was removed (didn't reflect what the school actually assigns).
    Returns per-week buckets (week_start, items, est_minutes, by_source)
    plus bucketing metadata. Pass child_id for one kid; otherwise both."""
    started = time.monotonic()
    err: str | None = None
    result: Any = None
    try:
        from sqlalchemy import select
        from ..models import Child
        from ..services.homework_load import homework_load, homework_load_all
        async with get_async_session() as session:
            if child_id is None:
                result = {
                    "kids": await homework_load_all(session, weeks=weeks),
                    "weeks": weeks,
                }
            else:
                child = (
                    await session.execute(select(Child).where(Child.id == child_id))
                ).scalar_one_or_none()
                if child is None:
                    raise ValueError(f"child {child_id} not found")
                result = await homework_load(
                    session, child,
                    weeks=weeks,
                    extra_minutes_per_item=extra_minutes_per_item,
                )
        return result
    except Exception as e:
        err = repr(e)
        raise
    finally:
        await _audit(
            "get_homework_load",
            {
                "child_id": child_id,
                "weeks": weeks,
                "extra_minutes_per_item": extra_minutes_per_item,
            },
            None, err, started, _client_id(ctx),
        )


# ───────────────────────── Worth-a-chat (PTM list) ─────────────────────────

@server.tool()
async def get_worth_a_chat(
    child_id: int | None = None,
    kind: str | None = None,
    limit: int = 200,
    ctx: Context | None = None,
) -> list[dict[str, Any]]:
    """Items the parent flagged as 'worth a chat' for the next parent-teacher
    meeting. Spans every kind (assignments, grades, comments, school
    messages). Each row carries `discuss_with_teacher_at` (ISO timestamp)
    + `discuss_with_teacher_note` (the parent's optional reason). Newest
    flag first. Use this to summarise what the parent wants to raise."""
    started = time.monotonic()
    err: str | None = None
    result: list[dict[str, Any]] = []
    try:
        async with get_async_session() as session:
            result = await Q.get_worth_a_chat(
                session, child_id=child_id, kind=kind, limit=limit,
            )
        return result
    except Exception as e:
        err = repr(e)
        raise
    finally:
        await _audit(
            "get_worth_a_chat",
            {"child_id": child_id, "kind": kind, "limit": limit},
            result, err, started, _client_id(ctx),
        )


@server.tool()
async def set_worth_a_chat(
    item_id: int,
    flag: bool,
    note: str | None = None,
    ctx: Context | None = None,
) -> dict[str, Any]:
    """Toggle the 'worth a chat' flag on any item (assignment, grade,
    comment, school message). When flag=True, the server stamps the
    timestamp; when False, it clears both the flag and the note.
    Setting `note` alone (with flag=True) updates the reason text in
    place. Audit log captures every change."""
    started = time.monotonic()
    err: str | None = None
    result: dict[str, Any] = {}
    try:
        from ..services import assignment_state as ast
        patch: dict[str, Any] = {"discuss_with_teacher": flag}
        if note is not None:
            patch["discuss_with_teacher_note"] = note
        async with get_async_session() as session:
            r = await ast.update_assignment_state(session, item_id, patch)
        if r is None:
            raise ValueError(f"item {item_id} not found, or non-assignment with non-flag fields")
        result = r
        return result
    except Exception as e:
        err = repr(e)
        raise
    finally:
        await _audit(
            "set_worth_a_chat",
            {"item_id": item_id, "flag": flag, "note": note},
            result, err, started, _client_id(ctx),
        )


# ───────────────────────── Briefs (Sunday / PTM / Daily) ─────────────────────────

@server.tool()
async def get_sunday_brief(
    child_id: int | None = None,
    refresh: bool = False,
    ctx: Context | None = None,
) -> dict[str, Any] | list[dict[str, Any]]:
    """Sunday brief — 4-section synthesis (cycle shape / one ask /
    teacher asks / what to ignore). Pre-warmed nightly at 02:00 IST
    and cached on disk under data/cached_briefs/sunday/. Pass child_id
    for one kid (full-shape dict) or omit for both (list). `refresh=True`
    skips the cache and re-runs Claude live (~30-60s)."""
    started = time.monotonic()
    err: str | None = None
    result: Any = None
    try:
        from sqlalchemy import select
        from ..models import Child
        from ..services import cached_briefs as CB
        from ..services.sunday_brief import build_brief, render_markdown
        from ..util.time import today_ist
        today = today_ist()
        async with get_async_session() as session:
            if child_id is None:
                children = (await session.execute(select(Child))).scalars().all()
                out: list[dict[str, Any]] = []
                for c in children:
                    slug = CB.child_slug_for(c.display_name, c.id)
                    cached = None if refresh else CB.read_latest("sunday", slug, today=today)
                    if cached:
                        cached["_cache"] = {
                            "hit": True,
                            "freshness": CB.freshness_label(today, cached.get("generated_for")),
                        }
                        out.append(cached)
                        continue
                    brief = await build_brief(session, c)
                    payload = brief.to_dict()
                    md = render_markdown(brief)
                    try:
                        CB.write_brief("sunday", slug, today, payload, md)
                    except Exception:
                        pass
                    payload["_cache"] = {"hit": False, "freshness": "today"}
                    out.append(payload)
                result = out
                return result
            child = (
                await session.execute(select(Child).where(Child.id == child_id))
            ).scalar_one_or_none()
            if child is None:
                raise ValueError(f"child {child_id} not found")
            slug = CB.child_slug_for(child.display_name, child.id)
            if not refresh:
                cached = CB.read_latest("sunday", slug, today=today)
                if cached:
                    cached["_cache"] = {
                        "hit": True,
                        "freshness": CB.freshness_label(today, cached.get("generated_for")),
                    }
                    result = cached
                    return result
            brief = await build_brief(session, child)
            payload = brief.to_dict()
            md = render_markdown(brief)
            try:
                CB.write_brief("sunday", slug, today, payload, md)
            except Exception:
                pass
            payload["_cache"] = {"hit": False, "freshness": "today"}
            result = payload
            return result
    except Exception as e:
        err = repr(e)
        raise
    finally:
        await _audit(
            "get_sunday_brief",
            {"child_id": child_id, "refresh": refresh},
            None, err, started, _client_id(ctx),
        )


@server.tool()
async def get_ptm_brief(
    child_id: int,
    refresh: bool = False,
    ctx: Context | None = None,
) -> dict[str, Any]:
    """Parent-Teacher Meeting brief for one kid — per-subject prep doc
    with current state, talking points, questions for each teacher, and
    the parent's flagged 'worth a chat' items. Cached nightly at 02:00
    IST under data/cached_briefs/ptm/. `refresh=True` skips cache and
    re-runs Claude (~30-60s). Returns headline, subjects[], general
    questions, things-to-ignore, parent_raised_general, honest_caveat."""
    started = time.monotonic()
    err: str | None = None
    result: dict[str, Any] = {}
    try:
        from sqlalchemy import select
        from ..models import Child
        from ..services import cached_briefs as CB
        from ..services.ptm_brief import build_ptm_brief, render_markdown
        from ..util.time import today_ist
        today = today_ist()
        async with get_async_session() as session:
            child = (
                await session.execute(select(Child).where(Child.id == child_id))
            ).scalar_one_or_none()
            if child is None:
                raise ValueError(f"child {child_id} not found")
            slug = CB.child_slug_for(child.display_name, child.id)
            if not refresh:
                cached = CB.read_latest("ptm", slug, today=today)
                if cached:
                    cached["_cache"] = {
                        "hit": True,
                        "freshness": CB.freshness_label(today, cached.get("generated_for")),
                    }
                    result = cached
                    return result
            brief = await build_ptm_brief(session, child)
            payload = brief.to_dict()
            md = render_markdown(brief)
            try:
                CB.write_brief("ptm", slug, today, payload, md)
            except Exception:
                pass
            payload["_cache"] = {"hit": False, "freshness": "today"}
            result = payload
            return result
    except Exception as e:
        err = repr(e)
        raise
    finally:
        await _audit(
            "get_ptm_brief", {"child_id": child_id, "refresh": refresh},
            None, err, started, _client_id(ctx),
        )


@server.tool()
async def get_daily_brief(
    child_id: int | None = None,
    refresh: bool = False,
    ctx: Context | None = None,
) -> dict[str, Any] | list[dict[str, Any]]:
    """Today-page 1-paragraph synthesis. Lightweight — no nightly
    cache, just an in-memory cache keyed by (child_id, date). Pass
    child_id for one kid (dict) or omit for both (list).
    Returns {summary, has_signal, pack_row_ids}."""
    started = time.monotonic()
    err: str | None = None
    result: Any = None
    try:
        from sqlalchemy import select
        from ..models import Child
        from ..services.daily_brief import build_daily_brief, invalidate_daily_brief_cache
        if refresh:
            invalidate_daily_brief_cache(child_id)
        async with get_async_session() as session:
            if child_id is None:
                children = (await session.execute(select(Child))).scalars().all()
                result = [
                    (await build_daily_brief(session, c)).to_dict() for c in children
                ]
                return result
            child = (
                await session.execute(select(Child).where(Child.id == child_id))
            ).scalar_one_or_none()
            if child is None:
                raise ValueError(f"child {child_id} not found")
            brief = await build_daily_brief(session, child)
            result = brief.to_dict()
            return result
    except Exception as e:
        err = repr(e)
        raise
    finally:
        await _audit(
            "get_daily_brief", {"child_id": child_id, "refresh": refresh},
            None, err, started, _client_id(ctx),
        )


# ───────────────────────── Anomalies + summaries ─────────────────────────

@server.tool()
async def get_anomalies(
    child_id: int | None = None, ctx: Context | None = None,
) -> list[dict[str, Any]]:
    """Off-trend grades that broke the kid's per-subject baseline (mean
    ± stddev). Each row: grade_id, subject, graded_date, pct, reason
    string ('drop_vs_trend' / 'spike_vs_trend' / etc). Read-only —
    call explain_grade_anomaly to add a Claude-driven hypothesis."""
    started = time.monotonic()
    err: str | None = None
    result: list[dict[str, Any]] = []
    try:
        from sqlalchemy import select
        from ..models import Child
        from ..services.anomaly import detect_anomalies_for_child
        async with get_async_session() as session:
            if child_id is None:
                children = (await session.execute(select(Child))).scalars().all()
                out: list[dict[str, Any]] = []
                for c in children:
                    out.extend(await detect_anomalies_for_child(session, c.id))
                result = out
            else:
                result = await detect_anomalies_for_child(session, child_id)
        return result
    except Exception as e:
        err = repr(e)
        raise
    finally:
        await _audit(
            "get_anomalies", {"child_id": child_id},
            result, err, started, _client_id(ctx),
        )


@server.tool()
async def explain_grade_anomaly(
    grade_id: int, force: bool = False, ctx: Context | None = None,
) -> dict[str, Any]:
    """Claude-driven hypothesis for an off-trend grade. Returns
    {grade_id, anomalous, reason, explanation, cached, llm_used}.
    Cached on the row's `llm_summary` column — call again with
    force=True to recompute."""
    started = time.monotonic()
    err: str | None = None
    result: dict[str, Any] = {}
    try:
        from ..services.anomaly import explain_grade_anomaly as fn
        async with get_async_session() as session:
            result = await fn(session, grade_id, force=force)
        return result
    except Exception as e:
        err = repr(e)
        raise
    finally:
        await _audit(
            "explain_grade_anomaly", {"grade_id": grade_id, "force": force},
            result, err, started, _client_id(ctx),
        )


@server.tool()
async def summarize_assignment(
    item_id: int, force: bool = False, ctx: Context | None = None,
) -> dict[str, Any]:
    """One-sentence 'the ask in plain English' for an assignment.
    Cached on the row's `llm_summary` column. Returns {item_id,
    summary, cached, llm_used}. force=True bypasses cache."""
    started = time.monotonic()
    err: str | None = None
    result: dict[str, Any] = {}
    try:
        from ..services.assignment_summary import summarize_assignment as fn
        async with get_async_session() as session:
            result = await fn(session, item_id, force=force)
        return result
    except Exception as e:
        err = repr(e)
        raise
    finally:
        await _audit(
            "summarize_assignment", {"item_id": item_id, "force": force},
            result, err, started, _client_id(ctx),
        )


@server.tool()
async def get_topic_detail(
    child_id: int, subject: str, topic: str, ctx: Context | None = None,
) -> dict[str, Any]:
    """Composite payload for one (kid × subject × topic): mastery state,
    every linked grade + assignment, portfolio attachments. Same data
    the syllabus topic-detail panel uses."""
    started = time.monotonic()
    err: str | None = None
    result: dict[str, Any] = {}
    try:
        # Reuse the FastAPI handler logic via direct service composition.
        from sqlalchemy import select
        from ..models import Child, TopicState, VeracrossItem
        from ..services.syllabus import fuzzy_topic_for
        from ..services.portfolio import list_portfolio
        from ..services.queries import _item_to_dict

        def _strip_lc(t: str) -> str:
            if t and ": " in t:
                head, tail = t.split(": ", 1)
                if head.strip().upper().startswith("LC"):
                    return tail.strip()
            return t.strip() if t else t

        async with get_async_session() as session:
            child = (
                await session.execute(select(Child).where(Child.id == child_id))
            ).scalar_one_or_none()
            if child is None:
                raise ValueError(f"child {child_id} not found")
            bare_topic = _strip_lc(topic)
            ts = (
                await session.execute(
                    select(TopicState)
                    .where(TopicState.child_id == child_id)
                    .where(TopicState.subject == subject)
                    .where(TopicState.topic == bare_topic)
                )
            ).scalar_one_or_none()
            items = (
                await session.execute(
                    select(VeracrossItem)
                    .where(VeracrossItem.child_id == child_id)
                    .where(VeracrossItem.kind.in_(("assignment", "grade")))
                )
            ).scalars().all()
            linked_grades: list[dict[str, Any]] = []
            linked_assignments: list[dict[str, Any]] = []
            for it in items:
                t = fuzzy_topic_for(child.class_level, it.subject, it.title)
                if t is None:
                    continue
                t_bare = _strip_lc(t)
                if t_bare != bare_topic:
                    continue
                d = _item_to_dict(it, class_level=child.class_level)
                if it.kind == "grade":
                    linked_grades.append(d)
                else:
                    linked_assignments.append(d)
            portfolio = await list_portfolio(
                session, child_id=child_id, subject=subject, topic=topic,
            )
        result = {
            "child_id": child_id,
            "subject": subject,
            "topic": topic,
            "bare_topic": bare_topic,
            "state": ts.state if ts else None,
            "last_assessed_at": ts.last_assessed_at if ts else None,
            "last_score": ts.last_score if ts else None,
            "attempt_count": ts.attempt_count if ts else 0,
            "proficient_count": ts.proficient_count if ts else 0,
            "language_code": ts.language_code if ts else None,
            "linked_grades": linked_grades,
            "linked_assignments": linked_assignments,
            "portfolio_items": portfolio,
        }
        return result
    except Exception as e:
        err = repr(e)
        raise
    finally:
        await _audit(
            "get_topic_detail",
            {"child_id": child_id, "subject": subject, "topic": topic},
            None, err, started, _client_id(ctx),
        )


# ───────────────────────── Self-prediction (Zimmerman loop) ─────────────────────────

@server.tool()
async def set_self_prediction(
    item_id: int, prediction: str | None, ctx: Context | None = None,
) -> dict[str, Any]:
    """Record the kid's pre-grade self-prediction band ("high"/"mid"/
    "low" or numeric "%85"). Pass None to clear. Outcome is computed
    automatically once the linked grade lands."""
    started = time.monotonic()
    err: str | None = None
    result: dict[str, Any] = {}
    try:
        from datetime import datetime, timezone as _tz
        from sqlalchemy import select
        from ..models import VeracrossItem
        from ..services import self_prediction as SP
        async with get_async_session() as session:
            item = (
                await session.execute(
                    select(VeracrossItem).where(VeracrossItem.id == item_id)
                )
            ).scalar_one_or_none()
            if item is None:
                raise ValueError(f"item {item_id} not found")
            if prediction is not None and not SP.is_valid_prediction(prediction):
                raise ValueError(f"invalid prediction: {prediction!r}")
            item.self_prediction = prediction or None
            item.self_prediction_set_at = (
                datetime.now(tz=_tz.utc) if prediction else None
            )
            if not prediction:
                item.self_prediction_outcome = None
            await session.commit()
            await session.refresh(item)
        result = {
            "item_id": item.id,
            "self_prediction": item.self_prediction,
            "self_prediction_set_at": (
                item.self_prediction_set_at.isoformat()
                if item.self_prediction_set_at else None
            ),
            "self_prediction_outcome": item.self_prediction_outcome,
        }
        return result
    except Exception as e:
        err = repr(e)
        raise
    finally:
        await _audit(
            "set_self_prediction", {"item_id": item_id, "prediction": prediction},
            result, err, started, _client_id(ctx),
        )


@server.tool()
async def get_self_prediction_calibration(
    child_id: int | None = None, ctx: Context | None = None,
) -> dict[str, Any]:
    """Aggregate calibration: how often the kid's predictions matched
    vs over/under. Returns summary + per-row history."""
    started = time.monotonic()
    err: str | None = None
    result: dict[str, Any] = {}
    try:
        from sqlalchemy import select
        from ..models import VeracrossItem
        from ..services import self_prediction as SP
        async with get_async_session() as session:
            q = (
                select(VeracrossItem)
                .where(VeracrossItem.self_prediction.is_not(None))
                .order_by(VeracrossItem.self_prediction_set_at.desc())
            )
            if child_id is not None:
                q = q.where(VeracrossItem.child_id == child_id)
            items = (await session.execute(q)).scalars().all()
        rows = [
            {
                "item_id": it.id,
                "child_id": it.child_id,
                "subject": it.subject,
                "title": it.title,
                "self_prediction": it.self_prediction,
                "self_prediction_outcome": it.self_prediction_outcome,
                "self_prediction_set_at": (
                    it.self_prediction_set_at.isoformat()
                    if it.self_prediction_set_at else None
                ),
            }
            for it in items
        ]
        result = {"summary": SP.calibration_summary(rows), "rows": rows}
        return result
    except Exception as e:
        err = repr(e)
        raise
    finally:
        await _audit(
            "get_self_prediction_calibration", {"child_id": child_id},
            None, err, started, _client_id(ctx),
        )


# ───────────────────────── School messages (grouped) ─────────────────────────

@server.tool()
async def get_school_messages_grouped(
    limit: int = 50, ctx: Context | None = None,
) -> list[dict[str, Any]]:
    """Dedup'd school-message groups (broadcast titles collapsed across
    kids). Each group: group_id, normalized_title, kids[], members[],
    cached llm_summary if computed. Newest first."""
    started = time.monotonic()
    err: str | None = None
    result: list[dict[str, Any]] = []
    try:
        from ..services.school_messages import list_grouped_messages
        async with get_async_session() as session:
            result = await list_grouped_messages(session, limit=limit)
        return result
    except Exception as e:
        err = repr(e)
        raise
    finally:
        await _audit(
            "get_school_messages_grouped", {"limit": limit},
            result, err, started, _client_id(ctx),
        )


@server.tool()
async def summarize_school_message_group(
    group_id: str, ctx: Context | None = None,
) -> dict[str, Any]:
    """Generate (or fetch cached) 1-sentence summary for a school-message
    group. Cached on every member row's `llm_summary` so re-calls are
    free. Returns {group_id, summary, url, members, llm_used}."""
    started = time.monotonic()
    err: str | None = None
    result: dict[str, Any] = {}
    try:
        from ..services.school_messages import summarize_group
        async with get_async_session() as session:
            r = await summarize_group(session, group_id)
        if r is None:
            raise ValueError(f"group {group_id!r} not found")
        result = r
        return result
    except Exception as e:
        err = repr(e)
        raise
    finally:
        await _audit(
            "summarize_school_message_group", {"group_id": group_id},
            result, err, started, _client_id(ctx),
        )


# ───────────────────────── Sentiment + heatmap ─────────────────────────

@server.tool()
async def get_sentiment_trend(
    child_id: int | None = None,
    window_days: int = 28,
    bucket_days: int = 7,
    ctx: Context | None = None,
) -> dict[str, Any]:
    """Rolling sentiment trend across teacher comments, bucketed weekly.
    Lexicon-based (services/sentiment.py — no LLM, no remote calls).
    Returns points[], total_comments, direction (rising/falling/flat),
    honest_caveat. Empty buckets are gaps, not zeros."""
    started = time.monotonic()
    err: str | None = None
    result: dict[str, Any] = {}
    try:
        from datetime import timedelta
        from sqlalchemy import select
        from ..models import VeracrossItem
        from ..services.sentiment import trend_points
        from ..services.grade_match import _parse_loose_date
        from ..util.time import today_ist
        today = today_ist()
        since = today - timedelta(days=window_days)
        async with get_async_session() as session:
            q = (
                select(VeracrossItem)
                .where(VeracrossItem.kind == "comment")
                .order_by(VeracrossItem.due_or_date.desc())
            )
            if child_id is not None:
                q = q.where(VeracrossItem.child_id == child_id)
            rows = (await session.execute(q)).scalars().all()
        items: list[tuple[Any, str]] = []
        for r in rows:
            d = _parse_loose_date(r.due_or_date)
            if d is None or d < since:
                continue
            text = (r.title_en or r.title or r.body or "").strip()
            if text:
                items.append((d, text))
        points = trend_points(
            items, today=today, window_days=window_days, bucket_days=bucket_days,
        )
        means = [p["mean_score"] for p in points if p.get("mean_score") is not None]
        direction: str | None = None
        if len(means) >= 2:
            delta = means[-1] - means[0]  # type: ignore
            direction = "rising" if delta > 0.15 else ("falling" if delta < -0.15 else "flat")
        result = {
            "points": points,
            "total_comments": len(items),
            "window_days": window_days,
            "bucket_days": bucket_days,
            "direction": direction,
            "honest_caveat": (
                "Per-comment sentiment is noisy; only the rolling trend is "
                "meaningful. Empty buckets are gaps, not zeros."
            ),
        }
        return result
    except Exception as e:
        err = repr(e)
        raise
    finally:
        await _audit(
            "get_sentiment_trend",
            {"child_id": child_id, "window_days": window_days, "bucket_days": bucket_days},
            None, err, started, _client_id(ctx),
        )


@server.tool()
async def get_submission_heatmap(
    child_id: int | None = None, weeks: int = 14, ctx: Context | None = None,
) -> list[dict[str, Any]]:
    """Submission-pattern heatmap — per-week × per-day-of-week tally
    of how often the kid was on-time / late / overdue. Used to show
    a 14-week visual; returns flat list of {week_start, dow, status,
    count} cells the caller groups."""
    started = time.monotonic()
    err: str | None = None
    result: list[dict[str, Any]] = []
    try:
        async with get_async_session() as session:
            result = await Q.get_submission_heatmap(
                session, child_id=child_id, weeks=weeks,
            )
        return result
    except Exception as e:
        err = repr(e)
        raise
    finally:
        await _audit(
            "get_submission_heatmap", {"child_id": child_id, "weeks": weeks},
            result, err, started, _client_id(ctx),
        )


# ───────────────────────── Notification snoozes ─────────────────────────

@server.tool()
async def list_notification_snoozes(ctx: Context | None = None) -> list[dict[str, Any]]:
    """Active (un-expired) parent-set snoozes per (rule_id, child_id).
    Used to show 'currently snoozed until …' on the (why?) popover."""
    started = time.monotonic()
    err: str | None = None
    result: list[dict[str, Any]] = []
    try:
        from datetime import datetime, timezone as _tz
        from sqlalchemy import select
        from ..models import NotificationSnooze
        async with get_async_session() as session:
            rows = (
                await session.execute(
                    select(NotificationSnooze)
                    .where(NotificationSnooze.until > datetime.now(tz=_tz.utc))
                    .order_by(NotificationSnooze.until.desc())
                )
            ).scalars().all()
        result = [
            {
                "id": r.id,
                "rule_id": r.rule_id,
                "child_id": r.child_id,
                "until": r.until.isoformat() if r.until else None,
                "reason": r.reason,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ]
        return result
    except Exception as e:
        err = repr(e)
        raise
    finally:
        await _audit(
            "list_notification_snoozes", {}, result, err, started, _client_id(ctx),
        )


@server.tool()
async def add_notification_snooze(
    rule_id: str,
    until: str,
    child_id: int | None = None,
    reason: str | None = None,
    ctx: Context | None = None,
) -> dict[str, Any]:
    """Snooze (rule_id, child_id) until ISO timestamp `until`. Idempotent
    upsert — newer `until` replaces older. child_id=None = kid-agnostic."""
    started = time.monotonic()
    err: str | None = None
    result: dict[str, Any] = {}
    try:
        from datetime import datetime, timezone as _tz
        from sqlalchemy import select
        from ..models import NotificationSnooze
        try:
            until_dt = datetime.fromisoformat(str(until).replace("Z", "+00:00"))
        except ValueError:
            raise ValueError(f"bad until: {until}")
        if until_dt.tzinfo is None:
            until_dt = until_dt.replace(tzinfo=_tz.utc)
        async with get_async_session() as session:
            existing = (
                await session.execute(
                    select(NotificationSnooze).where(
                        NotificationSnooze.rule_id == rule_id,
                        NotificationSnooze.child_id == child_id,
                    )
                )
            ).scalar_one_or_none()
            if existing:
                existing.until = until_dt
                if reason is not None:
                    existing.reason = reason
                row = existing
            else:
                row = NotificationSnooze(
                    rule_id=rule_id, child_id=child_id, until=until_dt, reason=reason,
                )
                session.add(row)
            await session.commit()
            await session.refresh(row)
        result = {
            "id": row.id, "rule_id": row.rule_id, "child_id": row.child_id,
            "until": row.until.isoformat(), "reason": row.reason,
        }
        return result
    except Exception as e:
        err = repr(e)
        raise
    finally:
        await _audit(
            "add_notification_snooze",
            {"rule_id": rule_id, "until": until, "child_id": child_id, "reason": reason},
            result, err, started, _client_id(ctx),
        )


@server.tool()
async def delete_notification_snooze(
    snooze_id: int, ctx: Context | None = None,
) -> dict[str, Any]:
    """Cancel an active snooze by id. Idempotent — returns ok=True
    even if the row was already expired or absent."""
    started = time.monotonic()
    err: str | None = None
    result: dict[str, Any] = {}
    try:
        from sqlalchemy import delete
        from ..models import NotificationSnooze
        async with get_async_session() as session:
            await session.execute(
                delete(NotificationSnooze).where(NotificationSnooze.id == snooze_id)
            )
            await session.commit()
        result = {"ok": True, "id": snooze_id}
        return result
    except Exception as e:
        err = repr(e)
        raise
    finally:
        await _audit(
            "delete_notification_snooze", {"snooze_id": snooze_id},
            result, err, started, _client_id(ctx),
        )


# ───────────────────────── Events (auditions, competitions, camps) ─────────────────────────

@server.tool()
async def list_events(
    child_id: int | None = None,
    days_ahead: int | None = None,
    include_past: bool = True,
    ctx: Context | None = None,
) -> list[dict[str, Any]]:
    """Kid-relevant events the parent has captured: auditions, exams,
    camps, competitions, parent meetings. `child_id=None` returns all
    (school-wide events have child_id=None). `days_ahead` caps the
    forward horizon; `include_past=False` drops events that already
    finished."""
    started = time.monotonic()
    err: str | None = None
    result: list[dict[str, Any]] = []
    try:
        from datetime import timedelta
        from ..services.kid_events import list_events as fn
        from ..util.time import today_ist
        today = today_ist()
        from_date = today if (days_ahead is not None or not include_past) else None
        to_date = (today + timedelta(days=days_ahead)) if days_ahead is not None else None
        async with get_async_session() as session:
            result = await fn(
                session, child_id=child_id,
                from_date=from_date, to_date=to_date,
                include_past=include_past,
            )
        return result
    except Exception as e:
        err = repr(e)
        raise
    finally:
        await _audit(
            "list_events",
            {"child_id": child_id, "days_ahead": days_ahead, "include_past": include_past},
            result, err, started, _client_id(ctx),
        )


@server.tool()
async def upsert_event(
    title: str,
    start_date: str,
    end_date: str | None = None,
    start_time: str | None = None,
    child_id: int | None = None,
    event_type: str | None = None,
    importance: int = 1,
    location: str | None = None,
    description: str | None = None,
    notes: str | None = None,
    source: str = "manual",
    source_ref: str | None = None,
    event_id: int | None = None,
    ctx: Context | None = None,
) -> dict[str, Any]:
    """Create or update a kid event. Pass `event_id` to update an
    existing row; omit to create. `start_date`/`end_date` are ISO
    YYYY-MM-DD; `start_time` is HH:MM. importance: 1 normal · 2
    important · 3 critical. event_type: audition | competition | camp
    | exam | holiday | parent_meeting | trip | other."""
    started = time.monotonic()
    err: str | None = None
    result: dict[str, Any] = {}
    try:
        from ..services.kid_events import upsert_event as fn
        payload = {
            "id": event_id,
            "child_id": child_id,
            "title": title,
            "description": description,
            "event_type": event_type,
            "importance": importance,
            "start_date": start_date,
            "end_date": end_date,
            "start_time": start_time,
            "location": location,
            "source": source,
            "source_ref": source_ref,
            "notes": notes,
        }
        async with get_async_session() as session:
            result = await fn(session, payload)
        return result
    except Exception as e:
        err = repr(e)
        raise
    finally:
        await _audit(
            "upsert_event", {"title": title, "start_date": start_date, "event_id": event_id},
            result, err, started, _client_id(ctx),
        )


@server.tool()
async def delete_event(event_id: int, ctx: Context | None = None) -> dict[str, Any]:
    """Permanently delete a kid event by id. Returns {ok, id}."""
    started = time.monotonic()
    err: str | None = None
    result: dict[str, Any] = {}
    try:
        from ..services.kid_events import delete_event as fn
        async with get_async_session() as session:
            ok = await fn(session, event_id)
        result = {"ok": ok, "id": event_id}
        return result
    except Exception as e:
        err = repr(e)
        raise
    finally:
        await _audit(
            "delete_event", {"event_id": event_id},
            result, err, started, _client_id(ctx),
        )


@server.tool()
async def extract_events_from_messages(
    days: int = 60,
    only_new: bool = True,
    ctx: Context | None = None,
) -> dict[str, Any]:
    """Sweep school messages from the last N days and ask Claude to
    extract dated events (auditions, camps, holidays, etc.). Idempotent
    — when `only_new=True`, skips messages we've already extracted from.
    Returns counts of {messages_scanned, events_extracted, inserted, skipped_dup}."""
    started = time.monotonic()
    err: str | None = None
    result: dict[str, Any] = {}
    try:
        from ..services.kid_events import extract_from_school_messages as fn
        async with get_async_session() as session:
            result = await fn(session, days=days, only_new=only_new)
        return result
    except Exception as e:
        err = repr(e)
        raise
    finally:
        await _audit(
            "extract_events_from_messages", {"days": days, "only_new": only_new},
            result, err, started, _client_id(ctx),
        )


# ───────────────────────── Library (parent uploads) ─────────────────────────

@server.tool()
async def list_library(
    child_id: int | None = None,
    kind: str | None = None,
    subject: str | None = None,
    ctx: Context | None = None,
) -> list[dict[str, Any]]:
    """Parent-uploaded files (textbook PDFs, EPUBs, study material).
    Each row carries the LLM classifier output (llm_kind, llm_subject,
    llm_summary, llm_keywords). kind/subject filters use the LLM-inferred
    values. Use read_library_file to fetch contents."""
    started = time.monotonic()
    err: str | None = None
    result: list[dict[str, Any]] = []
    try:
        from ..services.library import list_library as fn
        async with get_async_session() as session:
            result = await fn(session, child_id=child_id, kind=kind, subject=subject)
        return result
    except Exception as e:
        err = repr(e)
        raise
    finally:
        await _audit(
            "list_library", {"child_id": child_id, "kind": kind, "subject": subject},
            result, err, started, _client_id(ctx),
        )


@server.tool()
async def reclassify_library_file(
    library_id: int, ctx: Context | None = None,
) -> dict[str, Any]:
    """Re-run the LLM classifier on a library row (forces fresh
    llm_kind / llm_subject / llm_summary / llm_keywords / llm_class_level).
    Use after editing the file or to recover from a stale classification."""
    started = time.monotonic()
    err: str | None = None
    result: dict[str, Any] = {}
    try:
        from ..services.library_classify import classify_one
        async with get_async_session() as session:
            # classify_one is unconditional — re-running it overwrites
            # the previous llm_* columns regardless of staleness.
            r = await classify_one(session, library_id)
        result = r or {"id": library_id, "ok": False}
        return result
    except Exception as e:
        err = repr(e)
        raise
    finally:
        await _audit(
            "reclassify_library_file", {"library_id": library_id},
            result, err, started, _client_id(ctx),
        )


@server.tool()
async def delete_library_file(
    library_id: int, ctx: Context | None = None,
) -> dict[str, Any]:
    """Permanently delete a library file (DB row + on-disk blob).
    Returns {ok, id}."""
    started = time.monotonic()
    err: str | None = None
    result: dict[str, Any] = {}
    try:
        from ..services.library import delete_library
        async with get_async_session() as session:
            ok = await delete_library(session, library_id)
        result = {"ok": ok, "id": library_id}
        return result
    except Exception as e:
        err = repr(e)
        raise
    finally:
        await _audit(
            "delete_library_file", {"library_id": library_id},
            result, err, started, _client_id(ctx),
        )


# ───────────────────────── Portfolio (per-topic uploads) ─────────────────────────

@server.tool()
async def list_portfolio(
    child_id: int,
    subject: str | None = None,
    topic: str | None = None,
    ctx: Context | None = None,
) -> list[dict[str, Any]]:
    """Per-(subject, topic) portfolio attachments — photos, scans,
    drawings the parent uploaded against a syllabus topic. Bound by
    natural key (subject + topic strings) so the rows survive nightly
    topic_state rebuilds. Use read_portfolio_file to fetch contents."""
    started = time.monotonic()
    err: str | None = None
    result: list[dict[str, Any]] = []
    try:
        from ..services.portfolio import list_portfolio as fn
        async with get_async_session() as session:
            result = await fn(session, child_id=child_id, subject=subject, topic=topic)
        return result
    except Exception as e:
        err = repr(e)
        raise
    finally:
        await _audit(
            "list_portfolio",
            {"child_id": child_id, "subject": subject, "topic": topic},
            result, err, started, _client_id(ctx),
        )


@server.tool()
async def delete_portfolio_file(
    attachment_id: int, ctx: Context | None = None,
) -> dict[str, Any]:
    """Permanently delete a portfolio attachment. Only works for
    source_kind='portfolio_upload' rows; other attachments are
    rejected. Returns {ok, id}."""
    started = time.monotonic()
    err: str | None = None
    result: dict[str, Any] = {}
    try:
        from ..services.portfolio import delete_portfolio
        async with get_async_session() as session:
            ok = await delete_portfolio(session, attachment_id)
            await session.commit()
        result = {"ok": ok, "id": attachment_id}
        return result
    except Exception as e:
        err = repr(e)
        raise
    finally:
        await _audit(
            "delete_portfolio_file", {"attachment_id": attachment_id},
            result, err, started, _client_id(ctx),
        )


# ───────────────────────── Mindspark (Ei Mindspark progress) ─────────────────────────

@server.tool()
async def get_mindspark_progress(
    child_id: int | None = None, ctx: Context | None = None,
) -> dict[str, Any]:
    """Mindspark performance metrics scraped daily-ish: per-topic
    accuracy, mastery_level, recent session aggregates, daily snapshot
    (sparkies + section rank). NEVER includes question content — by
    design (see migration 0020 scope contract). Pass child_id for one
    kid, or omit for both. Returns {kids: [{child_id, child_name,
    sessions[], topics[]}]}."""
    started = time.monotonic()
    err: str | None = None
    result: dict[str, Any] = {}
    try:
        from sqlalchemy import select
        from ..models import Child, MindsparkSession, MindsparkTopicProgress
        async with get_async_session() as session:
            cq = select(Child).order_by(Child.id)
            if child_id is not None:
                cq = cq.where(Child.id == child_id)
            children = (await session.execute(cq)).scalars().all()
            kids = []
            for c in children:
                sessions = (
                    await session.execute(
                        select(MindsparkSession)
                        .where(MindsparkSession.child_id == c.id)
                        .order_by(MindsparkSession.started_at.desc())
                        .limit(50)
                    )
                ).scalars().all()
                topics = (
                    await session.execute(
                        select(MindsparkTopicProgress)
                        .where(MindsparkTopicProgress.child_id == c.id)
                        .order_by(MindsparkTopicProgress.last_activity_at.desc().nulls_last())
                    )
                ).scalars().all()
                kids.append({
                    "child_id": c.id,
                    "child_name": c.display_name,
                    "sessions": [
                        {
                            "id": s.id,
                            "external_id": s.external_id,
                            "subject": s.subject,
                            "topic_name": s.topic_name,
                            "started_at": s.started_at.isoformat() if s.started_at else None,
                            "duration_sec": s.duration_sec,
                            "questions_total": s.questions_total,
                            "questions_correct": s.questions_correct,
                            "accuracy_pct": s.accuracy_pct,
                        }
                        for s in sessions
                    ],
                    "topics": [
                        {
                            "id": t.id,
                            "subject": t.subject,
                            "topic_name": t.topic_name,
                            "topic_id": t.topic_id,
                            "accuracy_pct": t.accuracy_pct,
                            "questions_attempted": t.questions_attempted,
                            "time_spent_sec": t.time_spent_sec,
                            "mastery_level": t.mastery_level,
                            "last_activity_at": (
                                t.last_activity_at.isoformat() if t.last_activity_at else None
                            ),
                            "updated_at": t.updated_at.isoformat() if t.updated_at else None,
                        }
                        for t in topics
                    ],
                })
        result = {"kids": kids}
        return result
    except Exception as e:
        err = repr(e)
        raise
    finally:
        await _audit(
            "get_mindspark_progress", {"child_id": child_id},
            None, err, started, _client_id(ctx),
        )


@server.tool()
async def trigger_mindspark_sync(
    child_id: int | None = None, ctx: Context | None = None,
) -> dict[str, Any]:
    """Run the Mindspark scrape NOW (bypassing the every-3rd-day
    cadence). Slow — each kid takes ~60-90s including login + page
    settle. Mindspark has Imperva bot detection so this MUST run with
    full stealth posture. Returns per-kid status dicts."""
    started = time.monotonic()
    err: str | None = None
    result: dict[str, Any] = {}
    try:
        from ..scraper.mindspark.sync import run_metrics_for, run_metrics_all
        from sqlalchemy import select
        from ..models import Child
        async with get_async_session() as session:
            if child_id is None:
                result = await run_metrics_all()
            else:
                child = (
                    await session.execute(select(Child).where(Child.id == child_id))
                ).scalar_one_or_none()
                if child is None:
                    raise ValueError(f"child {child_id} not found")
                result = await run_metrics_for(session, child)
        return result
    except Exception as e:
        err = repr(e)
        raise
    finally:
        await _audit(
            "trigger_mindspark_sync", {"child_id": child_id},
            result, err, started, _client_id(ctx),
        )


# ───────────────────────── File downloads (read content) ─────────────────────────

# Cap on bytes returned in a single read_* call. MCP context size matters
# more than disk — anything larger than this should be read off-disk via
# resolve_*_path on a local client.
_READ_FILE_MAX_BYTES = 5 * 1024 * 1024  # 5 MB
_TEXT_MIMES = (
    "text/", "application/json", "application/xml", "application/x-yaml",
    "application/yaml",
)


def _read_file_payload(path: Any, mime_type: str | None) -> dict[str, Any]:
    """Shared helper for read_*_file tools. Returns:
      {filename, mime_type, size_bytes, encoding ('text'|'base64'),
       content, truncated}.
    Caps at _READ_FILE_MAX_BYTES; sets truncated=True if cut.
    Text-like MIME types return UTF-8 text; everything else returns
    base64 so binary survives the JSON wire format."""
    import base64
    from pathlib import Path as _P
    p = _P(path) if not isinstance(path, _P) else path
    full_size = p.stat().st_size
    raw = p.read_bytes()
    truncated = False
    if len(raw) > _READ_FILE_MAX_BYTES:
        raw = raw[:_READ_FILE_MAX_BYTES]
        truncated = True
    is_text = bool(mime_type) and any(mime_type.startswith(prefix) for prefix in _TEXT_MIMES)
    if is_text:
        try:
            content = raw.decode("utf-8")
            encoding = "text"
        except UnicodeDecodeError:
            content = base64.b64encode(raw).decode("ascii")
            encoding = "base64"
    else:
        content = base64.b64encode(raw).decode("ascii")
        encoding = "base64"
    return {
        "filename": p.name,
        "mime_type": mime_type or "application/octet-stream",
        "size_bytes": full_size,
        "encoding": encoding,
        "content": content,
        "truncated": truncated,
        "max_bytes": _READ_FILE_MAX_BYTES,
    }


@server.tool()
async def read_attachment(
    attachment_id: int, ctx: Context | None = None,
) -> dict[str, Any]:
    """Read the actual contents of a downloaded attachment. Returns
    {filename, mime_type, size_bytes, encoding, content, truncated}.
    Text-like files come back as UTF-8 strings; binaries (PDFs,
    images, zips) come back as base64. Capped at 5 MB — call
    resolve_attachment_path for larger files on local clients.
    Path-traversal guarded."""
    started = time.monotonic()
    err: str | None = None
    result: dict[str, Any] = {}
    try:
        from ..config import REPO_ROOT
        from ..util import paths as P
        async with get_async_session() as session:
            att = await Q.get_attachment_row(session, attachment_id)
        if att is None:
            raise ValueError(f"attachment {attachment_id} not found")
        path = (REPO_ROOT / att.local_path).resolve()
        try:
            path.relative_to(P.data_root().resolve())
        except ValueError:
            raise ValueError(f"attachment path escapes storage root: {att.local_path}")
        if not path.exists():
            raise ValueError(f"file vanished on disk: {att.local_path}")
        result = _read_file_payload(path, att.mime_type)
        result["attachment_id"] = att.id
        result["sha256"] = att.sha256
        return result
    except Exception as e:
        err = repr(e)
        raise
    finally:
        await _audit(
            "read_attachment", {"attachment_id": attachment_id},
            {"size_bytes": result.get("size_bytes"), "truncated": result.get("truncated")},
            err, started, _client_id(ctx),
        )


@server.tool()
async def read_library_file(
    library_id: int, ctx: Context | None = None,
) -> dict[str, Any]:
    """Read the actual contents of a library file. Same shape +
    truncation rules as read_attachment. Path-traversal guarded
    (file must live under data/library/)."""
    started = time.monotonic()
    err: str | None = None
    result: dict[str, Any] = {}
    try:
        from ..config import REPO_ROOT
        from ..services.library import get_library_row
        async with get_async_session() as session:
            row = await get_library_row(session, library_id)
        if row is None:
            raise ValueError(f"library file {library_id} not found")
        path = (REPO_ROOT / row.local_path).resolve()
        library_root = (REPO_ROOT / "data" / "library").resolve()
        if not str(path).startswith(str(library_root)):
            raise ValueError(f"library path escapes storage root: {row.local_path}")
        if not path.exists():
            raise ValueError(f"file vanished on disk: {row.local_path}")
        result = _read_file_payload(path, row.mime_type)
        result["library_id"] = row.id
        result["sha256"] = row.sha256
        return result
    except Exception as e:
        err = repr(e)
        raise
    finally:
        await _audit(
            "read_library_file", {"library_id": library_id},
            {"size_bytes": result.get("size_bytes"), "truncated": result.get("truncated")},
            err, started, _client_id(ctx),
        )


@server.tool()
async def read_portfolio_file(
    attachment_id: int, ctx: Context | None = None,
) -> dict[str, Any]:
    """Read the actual contents of a portfolio attachment (per-topic
    image/PDF). Same shape + truncation rules as read_attachment.
    Path-traversal guarded (file must live under data/portfolio/)."""
    started = time.monotonic()
    err: str | None = None
    result: dict[str, Any] = {}
    try:
        from sqlalchemy import select
        from ..config import REPO_ROOT
        from ..models import Attachment
        async with get_async_session() as session:
            att = (
                await session.execute(
                    select(Attachment).where(Attachment.id == attachment_id)
                )
            ).scalar_one_or_none()
        if att is None or att.source_kind != "portfolio_upload":
            raise ValueError(f"portfolio attachment {attachment_id} not found")
        path = (REPO_ROOT / att.local_path).resolve()
        portfolio_root = (REPO_ROOT / "data" / "portfolio").resolve()
        if not str(path).startswith(str(portfolio_root)):
            raise ValueError(f"portfolio path escapes storage root: {att.local_path}")
        if not path.exists():
            raise ValueError(f"file vanished on disk: {att.local_path}")
        result = _read_file_payload(path, att.mime_type)
        result["attachment_id"] = att.id
        result["sha256"] = att.sha256
        return result
    except Exception as e:
        err = repr(e)
        raise
    finally:
        await _audit(
            "read_portfolio_file", {"attachment_id": attachment_id},
            {"size_bytes": result.get("size_bytes"), "truncated": result.get("truncated")},
            err, started, _client_id(ctx),
        )


@server.tool()
async def read_resource_file(
    scope: str,
    category: str,
    filename: str,
    child_id: int | None = None,
    ctx: Context | None = None,
) -> dict[str, Any]:
    """Read a portal-harvested resource file. scope='schoolwide' or
    'kid' (kid requires child_id). Same shape + truncation rules as
    read_attachment. Path-traversal guarded (file must live under
    data/rawdata/)."""
    started = time.monotonic()
    err: str | None = None
    result: dict[str, Any] = {}
    try:
        from sqlalchemy import select
        from ..models import Child
        from ..services import resources_index as RI
        if scope == "schoolwide":
            path = RI.resolve_schoolwide(category, filename)
        elif scope == "kid":
            if child_id is None:
                raise ValueError("child_id required for scope='kid'")
            async with get_async_session() as session:
                child = (
                    await session.execute(select(Child).where(Child.id == child_id))
                ).scalar_one_or_none()
            if child is None:
                raise ValueError(f"child {child_id} not found")
            path = RI.resolve_kid(child, category, filename)
        else:
            raise ValueError(f"scope must be 'schoolwide' or 'kid', got {scope!r}")
        if path is None or not path.exists():
            raise ValueError(f"resource not found: {scope}/{category}/{filename}")
        mime = RI._mime(path)
        result = _read_file_payload(path, mime)
        result["scope"] = scope
        result["category"] = category
        return result
    except Exception as e:
        err = repr(e)
        raise
    finally:
        await _audit(
            "read_resource_file",
            {"scope": scope, "category": category, "filename": filename, "child_id": child_id},
            {"size_bytes": result.get("size_bytes"), "truncated": result.get("truncated")},
            err, started, _client_id(ctx),
        )


@server.tool()
async def read_spellbee_file(
    child_id: int, filename: str, ctx: Context | None = None,
) -> dict[str, Any]:
    """Read a Spelling Bee word-list file. Same shape + truncation
    rules as read_attachment. Path-traversal guarded — file must
    resolve under the kid's spellbee folder."""
    started = time.monotonic()
    err: str | None = None
    result: dict[str, Any] = {}
    try:
        from sqlalchemy import select
        from ..models import Child
        from ..services import spellbee as SB
        async with get_async_session() as session:
            child = (
                await session.execute(select(Child).where(Child.id == child_id))
            ).scalar_one_or_none()
        if child is None:
            raise ValueError(f"child {child_id} not found")
        path = SB.resolve_file(child, filename)
        if path is None or not path.exists():
            raise ValueError(f"spellbee list {filename!r} not found for child {child_id}")
        mime = SB._MIME_BY_EXT.get(path.suffix.lower(), "application/octet-stream")
        result = _read_file_payload(path, mime)
        result["child_id"] = child_id
        return result
    except Exception as e:
        err = repr(e)
        raise
    finally:
        await _audit(
            "read_spellbee_file", {"child_id": child_id, "filename": filename},
            {"size_bytes": result.get("size_bytes"), "truncated": result.get("truncated")},
            err, started, _client_id(ctx),
        )


# ───────────────────────── Gap-fill: assignments / sync / mindspark ─────────────────────────

@server.tool()
async def unmark_assignment_submitted(
    item_id: int, ctx: Context | None = None,
) -> dict[str, Any]:
    """Inverse of mark_assignment_submitted — clears the parent-side
    'submitted' override (the legacy parent_marked_submitted_at flag).
    The audit log captures the change."""
    started = time.monotonic()
    err: str | None = None
    result: dict[str, Any] = {}
    try:
        async with get_async_session() as session:
            r = await Q.mark_assignment_submitted(session, item_id, submitted=False)
        if r.get("status") == "not_found":
            raise ValueError(f"assignment {item_id} not found")
        result = r
        return result
    except Exception as e:
        err = repr(e)
        raise
    finally:
        await _audit(
            "unmark_assignment_submitted", {"item_id": item_id},
            result, err, started, _client_id(ctx),
        )


@server.tool()
async def prune_sync_runs(days: int = 7, ctx: Context | None = None) -> dict[str, Any]:
    """Drop sync_runs older than N days so log_text doesn't accumulate
    forever. Same operation as the nightly retention job, but on demand."""
    started = time.monotonic()
    err: str | None = None
    result: dict[str, Any] = {}
    try:
        from ..jobs.retention_job import prune_sync_logs
        result = await prune_sync_logs(days=days)
        return result
    except Exception as e:
        err = repr(e)
        raise
    finally:
        await _audit(
            "prune_sync_runs", {"days": days}, result, err, started, _client_id(ctx),
        )


@server.tool()
async def run_mindspark_recon(child_id: int, ctx: Context | None = None) -> dict[str, Any]:
    """Mindspark recon mode — login + walk parent-facing pages + dump
    every HTML/XHR under data/mindspark_recon/<child_id>/<ts>/. Used to
    refine the DOM parsers against real Ei output. SLOW (~3-5 min,
    full browser session); only call when you actually need a fresh
    dump for parser development."""
    started = time.monotonic()
    err: str | None = None
    result: dict[str, Any] = {}
    try:
        from ..scraper.mindspark.sync import run_recon_for
        result = await run_recon_for(child_id)
        return result
    except Exception as e:
        err = repr(e)
        raise
    finally:
        await _audit(
            "run_mindspark_recon", {"child_id": child_id},
            result, err, started, _client_id(ctx),
        )


# ───────────────────────── File uploads (base64 in) ─────────────────────────

# Same cap as the read tools — 5 MB per call. Enforced server-side
# regardless of what the client sends, so a misbehaving caller can't
# blow up the database with a giant blob.
_UPLOAD_MAX_BYTES = 5 * 1024 * 1024


def _decode_upload(content: str, encoding: str) -> bytes:
    """Decode an uploaded payload. encoding='base64' (default for any
    binary file) or 'text' (UTF-8 plain text). Caps at _UPLOAD_MAX_BYTES."""
    import base64
    if encoding == "text":
        data = content.encode("utf-8")
    elif encoding == "base64":
        try:
            data = base64.b64decode(content, validate=True)
        except Exception as e:
            raise ValueError(f"invalid base64 content: {e}")
    else:
        raise ValueError(f"encoding must be 'base64' or 'text', got {encoding!r}")
    if len(data) > _UPLOAD_MAX_BYTES:
        raise ValueError(
            f"upload {len(data)} bytes exceeds MCP cap of "
            f"{_UPLOAD_MAX_BYTES // (1024 * 1024)} MB"
        )
    return data


@server.tool()
async def upload_library_file(
    filename: str,
    content: str,
    encoding: str = "base64",
    child_id: int | None = None,
    note: str | None = None,
    ctx: Context | None = None,
) -> dict[str, Any]:
    """Upload a file to the parent-uploaded library (textbook PDFs, EPUB
    books, study material). `content` is base64-encoded by default —
    matches what `read_library_file` returns, so a round-trip works.
    Pass `encoding='text'` for plain text files (md / txt / csv) to
    skip the base64 step. Capped at 5 MB.

    Returns {id, filename, sha256, size_bytes, uploaded_at}. SHA-256
    dedup means re-uploading the same content reuses the existing row.
    LLM classification kicks off asynchronously — llm_* fields fill in
    a few seconds after the upload returns."""
    started = time.monotonic()
    err: str | None = None
    result: dict[str, Any] = {}
    try:
        data = _decode_upload(content, encoding)
        from ..services.library import save_library_upload
        async with get_async_session() as session:
            row = await save_library_upload(
                session,
                filename=filename, data=data,
                child_id=child_id, note=note,
            )
        result = {
            "id": row.id,
            "filename": row.filename,
            "sha256": row.sha256,
            "size_bytes": row.size_bytes,
            "mime_type": row.mime_type,
            "child_id": row.child_id,
            "uploaded_at": row.uploaded_at.isoformat() if row.uploaded_at else None,
        }
        return result
    except Exception as e:
        err = repr(e)
        raise
    finally:
        await _audit(
            "upload_library_file",
            {"filename": filename, "encoding": encoding,
             "child_id": child_id, "size_hint": len(content)},
            result, err, started, _client_id(ctx),
        )


@server.tool()
async def upload_portfolio_file(
    child_id: int,
    subject: str,
    topic: str,
    filename: str,
    content: str,
    encoding: str = "base64",
    note: str | None = None,
    ctx: Context | None = None,
) -> dict[str, Any]:
    """Upload a per-(subject, topic) portfolio attachment for a kid —
    images / scans / drawings / PDFs the parent wants the cockpit to
    track against a syllabus topic. Same content/encoding semantics as
    upload_library_file. Capped at 5 MB. SHA-256 dedup against
    (child × subject × topic) keeps duplicates from accumulating."""
    started = time.monotonic()
    err: str | None = None
    result: dict[str, Any] = {}
    try:
        data = _decode_upload(content, encoding)
        from sqlalchemy import select
        from ..models import Child
        from ..services.portfolio import save_portfolio_upload
        async with get_async_session() as session:
            child = (
                await session.execute(select(Child).where(Child.id == child_id))
            ).scalar_one_or_none()
            if child is None:
                raise ValueError(f"child {child_id} not found")
            row = await save_portfolio_upload(
                session, child, subject, topic, filename, data, note=note,
            )
            await session.commit()
        result = {
            "id": row.id,
            "child_id": row.child_id,
            "subject": row.topic_subject,
            "topic": row.topic_topic,
            "filename": row.filename,
            "sha256": row.sha256,
            "size_bytes": row.size_bytes,
            "mime_type": row.mime_type,
            "uploaded_at": row.downloaded_at.isoformat() if row.downloaded_at else None,
        }
        return result
    except Exception as e:
        err = repr(e)
        raise
    finally:
        await _audit(
            "upload_portfolio_file",
            {"child_id": child_id, "subject": subject, "topic": topic,
             "filename": filename, "encoding": encoding, "size_hint": len(content)},
            result, err, started, _client_id(ctx),
        )


@server.tool()
async def upload_spellbee_file(
    child_id: int,
    filename: str,
    content: str,
    encoding: str = "base64",
    ctx: Context | None = None,
) -> dict[str, Any]:
    """Upload a Spelling Bee word-list file (PDF / image / text) for a
    specific kid. The list-number is auto-detected from the filename
    (e.g. `list07.pdf` → number=7). Same content/encoding semantics as
    upload_library_file. Capped at 5 MB."""
    started = time.monotonic()
    err: str | None = None
    result: dict[str, Any] = {}
    try:
        data = _decode_upload(content, encoding)
        from sqlalchemy import select
        from ..models import Child
        from ..services import spellbee as SB
        async with get_async_session() as session:
            child = (
                await session.execute(select(Child).where(Child.id == child_id))
            ).scalar_one_or_none()
        if child is None:
            raise ValueError(f"child {child_id} not found")
        row = SB.save_upload(child, filename, data)
        result = {
            "filename": row.filename,
            "number": row.number,
            "size_bytes": row.size_bytes,
            "mime_type": row.mime_type,
            "child_id": row.child_id,
            "kid_slug": row.kid_slug,
            "download_url": row.download_url,
        }
        return result
    except Exception as e:
        err = repr(e)
        raise
    finally:
        await _audit(
            "upload_spellbee_file",
            {"child_id": child_id, "filename": filename,
             "encoding": encoding, "size_hint": len(content)},
            result, err, started, _client_id(ctx),
        )


# ───────────────────────── Schoolwork classifier + scheduler + syllabus validator ─────────────────────────

@server.tool()
async def classify_schoolwork_kind(
    item_id: int, ctx: Context | None = None,
) -> dict[str, Any]:
    """Classify a single assignment as new_work / review / test / project /
    presentation / submission / other based on its title + body.
    Deterministic keyword pass — no LLM call. Returns
    {item_id, kind, confidence, reasoning, matched_keywords}."""
    started = time.monotonic()
    err: str | None = None
    result: dict[str, Any] = {}
    try:
        from sqlalchemy import select
        from ..models import VeracrossItem
        from ..services.schoolwork_kind import classify
        async with get_async_session() as session:
            item = (
                await session.execute(
                    select(VeracrossItem).where(VeracrossItem.id == item_id)
                )
            ).scalar_one_or_none()
        if item is None:
            raise ValueError(f"item {item_id} not found")
        kr = classify(item.title or item.title_en, item.body or item.notes_en)
        result = {
            "item_id": item.id,
            "title": item.title,
            "subject": item.subject,
            "due_or_date": item.due_or_date,
            **kr.to_dict(),
        }
        return result
    except Exception as e:
        err = repr(e)
        raise
    finally:
        await _audit(
            "classify_schoolwork_kind", {"item_id": item_id},
            result, err, started, _client_id(ctx),
        )


@server.tool()
async def get_schedule_for_date(
    date_iso: str,
    subject: str | None = None,
    child_id: int | None = None,
    classify_kinds: bool = True,
    ctx: Context | None = None,
) -> dict[str, Any]:
    """Every assignment due on a specific calendar date, optionally
    filtered to one subject and/or one kid. With `classify_kinds=true`
    (default), each row is tagged with its schoolwork_kind so the caller
    can distinguish "Wednesday's social studies — review of Chapter 4"
    from "Wednesday's social studies — new chapter".

    Args:
      date_iso     ISO YYYY-MM-DD
      subject      optional — exact subject (cleaned, e.g. "Social Studies")
      child_id     optional — restrict to one kid
      classify_kinds  default true; pass false for raw rows

    Returns {date, count, by_subject, items}."""
    started = time.monotonic()
    err: str | None = None
    result: dict[str, Any] = {}
    try:
        from datetime import date as _date
        from sqlalchemy import or_, select
        from ..models import VeracrossItem
        from ..services.queries import _item_to_dict, _child_class_levels
        from ..services.schoolwork_kind import classify_batch
        try:
            target = _date.fromisoformat(date_iso)
        except ValueError:
            raise ValueError(f"date_iso must be YYYY-MM-DD, got {date_iso!r}")
        async with get_async_session() as session:
            q = (
                select(VeracrossItem)
                .where(VeracrossItem.kind == "assignment")
                .where(VeracrossItem.due_or_date == target.isoformat())
                .order_by(VeracrossItem.subject, VeracrossItem.title)
            )
            if child_id is not None:
                q = q.where(VeracrossItem.child_id == child_id)
            if subject:
                q = q.where(
                    or_(
                        VeracrossItem.subject == subject,
                        VeracrossItem.subject.like(f"% {subject}"),
                    )
                )
            class_levels = await _child_class_levels(session)
            items = (await session.execute(q)).scalars().all()
            rows = [
                _item_to_dict(r, class_level=class_levels.get(r.child_id))
                for r in items
            ]
        if classify_kinds:
            rows = classify_batch(rows)
        by_subject: dict[str, int] = {}
        for r in rows:
            s = r.get("subject") or "—"
            by_subject[s] = by_subject.get(s, 0) + 1
        result = {
            "date": target.isoformat(),
            "weekday": target.strftime("%A"),
            "count": len(rows),
            "by_subject": by_subject,
            "items": rows,
        }
        return result
    except Exception as e:
        err = repr(e)
        raise
    finally:
        await _audit(
            "get_schedule_for_date",
            {"date_iso": date_iso, "subject": subject, "child_id": child_id,
             "classify_kinds": classify_kinds},
            None, err, started, _client_id(ctx),
        )


@server.tool()
async def validate_syllabus(
    class_level: int | None = None, ctx: Context | None = None,
) -> dict[str, Any] | list[dict[str, Any]]:
    """Run structural checks on a class's syllabus JSON file. Catches:
      - cycle date overlaps + gaps + unsorted-by-start
      - non-ISO dates / malformed cycle entries
      - empty subjects / empty topic lists
      - duplicate topics within a subject
      - leading/trailing whitespace on topic strings
      - mojibake markers (likely UTF-8 round-trip bugs)
      - filename ↔ JSON class_level mismatch

    Pass `class_level` for one report; omit to validate every syllabus
    file under data/syllabus/. Returns
      {class_level, file_path, file_exists, issues, summary, ok}.
    Each issue is {severity (error/warning/info), where, message}."""
    started = time.monotonic()
    err: str | None = None
    result: Any = None
    try:
        from ..services.syllabus_validate import validate, validate_all
        if class_level is None:
            result = validate_all()
        else:
            result = validate(class_level).to_dict()
        return result
    except Exception as e:
        err = repr(e)
        raise
    finally:
        await _audit(
            "validate_syllabus", {"class_level": class_level},
            None, err, started, _client_id(ctx),
        )


# ───────────────────────── Practice-prep sessions (iterative cowork) ─────────────────────────

@server.tool()
async def start_practice_session(
    child_id: int,
    subject: str,
    topic: str | None = None,
    linked_assignment_id: int | None = None,
    title: str | None = None,
    initial_prompt: str | None = None,
    kind: str = "review_prep",
    use_llm: bool = True,
    ctx: Context | None = None,
) -> dict[str, Any]:
    """Spin up a new practice-prep workspace and run the FIRST iteration.

    Two flavours via `kind`:
      review_prep     — generates a practice sheet of questions for an
                        upcoming review/test (default)
      assignment_help — generates support material (outline / hints /
                        worked example / reading guide) for an
                        existing assignment the kid has to do

    Both share the same iteration + classwork-scan plumbing.

    Returns the full session payload (incl. `iterations[0]` = initial draft).
    Pass `linked_assignment_id` to ground the prep against a specific
    upcoming review/test row OR the assignment to be helped. Pass `topic`
    for free-form study not tied to an assignment. `initial_prompt` lets
    you steer the first round explicitly.

    `use_llm=False` skips the Opus call and produces a rule skeleton —
    handy when offline or when you want to seed the workspace cheaply
    before iterating."""
    started = time.monotonic()
    err: str | None = None
    result: dict[str, Any] = {}
    try:
        from ..services.practice_session import start_session
        async with get_async_session() as session:
            result = await start_session(
                session,
                child_id=child_id, subject=subject, topic=topic,
                linked_assignment_id=linked_assignment_id,
                title=title, initial_prompt=initial_prompt,
                kind=kind, use_llm=use_llm,
            )
        return result
    except Exception as e:
        err = repr(e)
        raise
    finally:
        await _audit(
            "start_practice_session",
            {"child_id": child_id, "subject": subject, "topic": topic,
             "linked_assignment_id": linked_assignment_id,
             "use_llm": use_llm},
            None, err, started, _client_id(ctx),
        )


@server.tool()
async def iterate_practice_session(
    session_id: int,
    parent_prompt: str,
    use_llm: bool = True,
    ctx: Context | None = None,
) -> dict[str, Any]:
    """Append one more iteration steered by `parent_prompt` ("harder",
    "remove Q3", "more word problems", "in Hindi", "fewer marks").
    The LLM sees the prior iteration's draft + the parent's prompt and
    refines rather than regenerating from scratch.

    Returns the full session with the new iteration appended. The new
    iteration becomes the preferred draft automatically (use
    set_preferred_practice_iteration to revert)."""
    started = time.monotonic()
    err: str | None = None
    result: dict[str, Any] = {}
    try:
        from ..services.practice_session import iterate
        async with get_async_session() as session:
            result = await iterate(
                session, session_id,
                parent_prompt=parent_prompt, use_llm=use_llm,
            )
        return result
    except Exception as e:
        err = repr(e)
        raise
    finally:
        await _audit(
            "iterate_practice_session",
            {"session_id": session_id, "parent_prompt_len": len(parent_prompt or ""),
             "use_llm": use_llm},
            None, err, started, _client_id(ctx),
        )


@server.tool()
async def get_practice_session(
    session_id: int, ctx: Context | None = None,
) -> dict[str, Any]:
    """Full payload for one prep session — every iteration's markdown
    + parsed JSON, every classwork scan with extraction summary, the
    preferred-iteration pointer, and metadata."""
    started = time.monotonic()
    err: str | None = None
    result: dict[str, Any] = {}
    try:
        from ..services.practice_session import get_session
        async with get_async_session() as session:
            result = await get_session(session, session_id)
        return result
    except Exception as e:
        err = repr(e)
        raise
    finally:
        await _audit(
            "get_practice_session", {"session_id": session_id},
            None, err, started, _client_id(ctx),
        )


@server.tool()
async def list_practice_sessions(
    child_id: int | None = None,
    subject: str | None = None,
    include_archived: bool = False,
    limit: int = 100,
    ctx: Context | None = None,
) -> list[dict[str, Any]]:
    """Listing view — one row per session, no per-iteration content.
    Use get_practice_session(id) to drill into a specific workspace."""
    started = time.monotonic()
    err: str | None = None
    result: list[dict[str, Any]] = []
    try:
        from ..services.practice_session import list_sessions
        async with get_async_session() as session:
            result = await list_sessions(
                session, child_id=child_id, subject=subject,
                include_archived=include_archived, limit=limit,
            )
        return result
    except Exception as e:
        err = repr(e)
        raise
    finally:
        await _audit(
            "list_practice_sessions",
            {"child_id": child_id, "subject": subject,
             "include_archived": include_archived, "limit": limit},
            result, err, started, _client_id(ctx),
        )


@server.tool()
async def archive_practice_session(
    session_id: int,
    archive: bool = True,
    ctx: Context | None = None,
) -> dict[str, Any]:
    """Soft-archive (or un-archive) a session. Archived sessions hide
    from list_practice_sessions by default but stay queryable via
    include_archived=True. Pass `archive=False` to restore."""
    started = time.monotonic()
    err: str | None = None
    result: dict[str, Any] = {}
    try:
        from ..services.practice_session import archive_session
        async with get_async_session() as session:
            result = await archive_session(session, session_id, archive=archive)
        return result
    except Exception as e:
        err = repr(e)
        raise
    finally:
        await _audit(
            "archive_practice_session",
            {"session_id": session_id, "archive": archive},
            None, err, started, _client_id(ctx),
        )


@server.tool()
async def set_preferred_practice_iteration(
    iteration_id: int, ctx: Context | None = None,
) -> dict[str, Any]:
    """Star a specific iteration as the canonical draft for its session
    (overrides the latest-wins default). Useful when iteration N+2 was
    a regression and you want to revert to N+1."""
    started = time.monotonic()
    err: str | None = None
    result: dict[str, Any] = {}
    try:
        from ..services.practice_session import set_preferred
        async with get_async_session() as session:
            result = await set_preferred(session, iteration_id)
        return result
    except Exception as e:
        err = repr(e)
        raise
    finally:
        await _audit(
            "set_preferred_practice_iteration", {"iteration_id": iteration_id},
            None, err, started, _client_id(ctx),
        )


@server.tool()
async def upload_classwork_scan(
    child_id: int,
    subject: str,
    filename: str,
    content: str,
    encoding: str = "base64",
    session_id: int | None = None,
    extract: bool = True,
    ctx: Context | None = None,
) -> dict[str, Any]:
    """Upload a classwork scan (notebook page, blackboard photo, PDF
    worksheet) to ground the practice generator. Same {content, encoding}
    shape as upload_library_file. With `extract=true` (default) Claude
    Vision runs inline and returns the parsed summary + topics; pass
    `extract=false` to skip the Vision call (e.g. when you already have
    extracted text from another source).

    Bind to a session via `session_id`, or upload free-floating and
    bind later with bind_classwork_scan. Allowed: image/* + PDF; cap 10 MB."""
    started = time.monotonic()
    err: str | None = None
    result: dict[str, Any] = {}
    try:
        import base64 as _b64
        from sqlalchemy import select
        from ..models import Child
        if encoding == "text":
            data = content.encode("utf-8")
        elif encoding == "base64":
            try:
                data = _b64.b64decode(content, validate=True)
            except Exception as decode_err:
                raise ValueError(f"invalid base64 content: {decode_err}")
        else:
            raise ValueError(f"encoding must be 'base64' or 'text', got {encoding!r}")
        from ..services.classwork_scan import save_scan
        async with get_async_session() as session:
            child = (
                await session.execute(select(Child).where(Child.id == child_id))
            ).scalar_one_or_none()
            if child is None:
                raise ValueError(f"child {child_id} not found")
            result = await save_scan(
                session, child,
                subject=subject, filename=filename, data=data,
                session_id=session_id, extract=extract,
            )
        return result
    except Exception as e:
        err = repr(e)
        raise
    finally:
        await _audit(
            "upload_classwork_scan",
            {"child_id": child_id, "subject": subject, "filename": filename,
             "encoding": encoding, "session_id": session_id, "extract": extract,
             "size_hint": len(content)},
            result, err, started, _client_id(ctx),
        )


@server.tool()
async def list_classwork_scans(
    child_id: int | None = None,
    subject: str | None = None,
    session_id: int | None = None,
    unbound_only: bool = False,
    limit: int = 100,
    ctx: Context | None = None,
) -> list[dict[str, Any]]:
    """List classwork scans, filtered by kid / subject / bound session.
    `unbound_only=true` returns only scans not yet attached to any
    practice session (so the parent can sweep them into a workspace)."""
    started = time.monotonic()
    err: str | None = None
    result: list[dict[str, Any]] = []
    try:
        from ..services.classwork_scan import list_scans
        async with get_async_session() as session:
            result = await list_scans(
                session,
                child_id=child_id, subject=subject,
                session_id=session_id, unbound_only=unbound_only,
                limit=limit,
            )
        return result
    except Exception as e:
        err = repr(e)
        raise
    finally:
        await _audit(
            "list_classwork_scans",
            {"child_id": child_id, "subject": subject,
             "session_id": session_id, "unbound_only": unbound_only,
             "limit": limit},
            result, err, started, _client_id(ctx),
        )


@server.tool()
async def bind_classwork_scan(
    scan_id: int,
    practice_session_id: int | None,
    ctx: Context | None = None,
) -> dict[str, Any]:
    """Move a scan in/out of a practice session. Pass
    `practice_session_id=null` to detach. The next practice iteration
    in the bound session picks up the scan as grounding context."""
    started = time.monotonic()
    err: str | None = None
    result: dict[str, Any] = {}
    try:
        from ..services.classwork_scan import bind_scan
        async with get_async_session() as session:
            result = await bind_scan(session, scan_id, practice_session_id)
        return result
    except Exception as e:
        err = repr(e)
        raise
    finally:
        await _audit(
            "bind_classwork_scan",
            {"scan_id": scan_id, "practice_session_id": practice_session_id},
            result, err, started, _client_id(ctx),
        )


@server.tool()
async def delete_classwork_scan(
    scan_id: int, ctx: Context | None = None,
) -> dict[str, Any]:
    """Permanently delete a classwork scan + its underlying attachment
    row. The on-disk file is left in place (retention job sweeps it
    later). Returns {ok, id}."""
    started = time.monotonic()
    err: str | None = None
    result: dict[str, Any] = {}
    try:
        from ..services.classwork_scan import delete_scan
        async with get_async_session() as session:
            ok = await delete_scan(session, scan_id)
        result = {"ok": ok, "id": scan_id}
        return result
    except Exception as e:
        err = repr(e)
        raise
    finally:
        await _audit(
            "delete_classwork_scan", {"scan_id": scan_id},
            result, err, started, _client_id(ctx),
        )


def run_stdio() -> None:
    """Entry point for `schoolwork-mcp` — stdio transport, for Claude Desktop/Code."""
    asyncio.run(server.run_stdio_async())


if __name__ == "__main__":
    run_stdio()
