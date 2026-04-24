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
        "Parent-facing tracker for Vasant Valley School's Veracross portal. "
        "Use list_children first. For backlog questions use get_overdue / get_due_today / "
        "get_upcoming. For free-form questions across any unstructured content "
        "(teacher comments, school messages, articles, parent notes) use `ask`. "
        "To change an assignment's parent-side state (mark done-at-home, snooze, "
        "priority, tags, notes) use update_assignment — call get_assignment_constants "
        "first to see the allowed parent_status enum + tag vocabulary. "
        "For files use list_attachments; for Spelling Bee word lists use list_spellbee_lists. "
        "For sync observability use get_sync_runs + get_sync_run_log. "
        "Numbers and dates are authoritative; do not invent data not returned by a tool."
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
async def list_spellbee_lists(ctx: Context | None = None) -> list[dict[str, Any]]:
    """Spelling Bee word lists stored in data/spellbee/. Each entry has the
    parsed list number (or null) plus a download_url for fetching the file."""
    started = time.monotonic()
    err: str | None = None
    result: list[dict[str, Any]] = []
    try:
        from ..services import spellbee as SB
        result = [x.to_dict() for x in SB.list_lists()]
        return result
    except Exception as e:
        err = repr(e)
        raise
    finally:
        await _audit("list_spellbee_lists", {}, result, err, started, _client_id(ctx))


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


def run_stdio() -> None:
    """Entry point for `schoolwork-mcp` — stdio transport, for Claude Desktop/Code."""
    asyncio.run(server.run_stdio_async())


if __name__ == "__main__":
    run_stdio()
