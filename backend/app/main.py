"""FastAPI app — web API + mounted MCP server.

Transports:
  * HTTP GET/POST on /api/*             — web API for the React frontend
  * Streamable-HTTP at /mcp             — for Dispatch/OpenClaw/remote MCP clients
  * SSE at /mcp/sse                     — legacy SSE MCP transport (kept for compat)

Stdio transport is a separate entry point (`schoolwork-mcp`) in backend/app/mcp/server.py.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Annotated, Any

from fastapi import BackgroundTasks, Depends, FastAPI, File, HTTPException, Header, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse

from .config import get_settings
from .db import get_async_session
from .jobs.scheduler import start_scheduler, stop_scheduler
from .mcp.server import server as mcp_server
from .notability.dispatcher import load_config, save_config
from .scraper.sync import run_sync
from .services import queries as Q
from .services.briefing import generate_and_store_digest
from .services.render import render_for_digest
from .util.time import today_ist

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):  # noqa: ANN001
    # MCP server's session_manager must run its own lifespan (for streamable-http).
    async with mcp_server.session_manager.run():
        # Close any sync_run rows that got orphaned at status=running when
        # the previous server process exited. Happens on crash or kill -9.
        try:
            from .scraper.sync import _cleanup_stale_runs
            closed = await _cleanup_stale_runs(older_than_min=0)
            if closed:
                import logging as _l
                _l.getLogger(__name__).info(
                    "startup: closed %d orphaned running sync_run rows", closed,
                )
        except Exception:
            import logging as _l
            _l.getLogger(__name__).exception("startup stale-run cleanup failed")
        start_scheduler()
        try:
            yield
        finally:
            stop_scheduler()


app = FastAPI(
    title="Parent Cockpit",
    version="0.2.0",
    description="Veracross-fed tracker for Tejas & Samarth — see docs/BUILDSPEC.md",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r".*",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─── auth for MCP endpoints ──────────────────────────────────────────────────

async def require_mcp_bearer(
    authorization: Annotated[str | None, Header()] = None,
) -> None:
    expected = settings.mcp_bearer_token
    if not expected:
        # No token configured → allow (dev mode). In prod, set MCP_BEARER_TOKEN.
        return
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing bearer token")
    provided = authorization.split(None, 1)[1].strip()
    if provided != expected:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid bearer token")


# ─── health + web API ─────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def today_html() -> str:
    """Live Today view — the same shape as the digest, rendered as HTML."""
    data = await generate_and_store_digest(kind="digest_preview", llm=False)
    rendered = render_for_digest(data)
    page = f"""<!doctype html>
<html lang="en"><head>
<meta charset="utf-8">
<title>Parent Cockpit — Today</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
  body {{ background:#fafafa; color:#222; font-family: ui-sans-serif, system-ui, sans-serif; margin:0; padding:20px; }}
  .topbar {{ display:flex; justify-content:space-between; align-items:center; margin-bottom:20px; }}
  .topbar a {{ color:#036; text-decoration:none; margin-left:16px; font-size:14px; }}
  form {{ display:inline; }}
  button {{ background:#036; color:#fff; border:0; padding:6px 14px; border-radius:4px; cursor:pointer; }}
  .wrap {{ background:#fff; border:1px solid #eee; border-radius:8px; padding:20px; }}
</style>
</head><body>
<div class="topbar">
  <h1 style="margin:0">🏫 Parent Cockpit</h1>
  <div>
    <a href="/api/notifications">Notifications JSON</a>
    <a href="/api/channel-config">Settings</a>
    <a href="/docs">API Docs</a>
    <form action="/api/sync" method="post">
      <button type="submit">Sync now</button>
    </form>
    <form action="/api/digest/run" method="post">
      <button type="submit">Send digest</button>
    </form>
  </div>
</div>
<div class="wrap">
{rendered['html']}
</div>
</body></html>"""
    return page


@app.get("/health")
async def health() -> dict[str, Any]:
    async with get_async_session() as session:
        last_sync = await Q.get_latest_sync(session)
        children = await Q.list_children(session)
    return {
        "status": "ok",
        "version": "0.2.0",
        "children_count": len(children),
        "last_sync": last_sync,
        "mcp_auth_required": bool(settings.mcp_bearer_token),
    }


@app.get("/api/children")
async def api_children() -> list[dict[str, Any]]:
    async with get_async_session() as session:
        return await Q.list_children(session)


@app.get("/api/today")
async def api_today() -> dict[str, Any]:
    async with get_async_session() as session:
        return await Q.get_today(session)


@app.get("/api/overdue")
async def api_overdue(child_id: int | None = None) -> list[dict[str, Any]]:
    async with get_async_session() as session:
        return await Q.get_overdue(session, child_id=child_id)


@app.get("/api/due-today")
async def api_due_today(child_id: int | None = None) -> list[dict[str, Any]]:
    async with get_async_session() as session:
        return await Q.get_due_today(session, child_id=child_id)


@app.get("/api/upcoming")
async def api_upcoming(child_id: int | None = None, days: int = 14) -> list[dict[str, Any]]:
    async with get_async_session() as session:
        return await Q.get_upcoming(session, child_id=child_id, days=days)


@app.get("/api/grades")
async def api_grades(child_id: int, subject: str | None = None) -> list[dict[str, Any]]:
    async with get_async_session() as session:
        return await Q.get_grades(session, child_id=child_id, subject=subject)


@app.get("/api/grade-trends")
async def api_grade_trends(child_id: int) -> list[dict[str, Any]]:
    async with get_async_session() as session:
        return await Q.get_grade_trends(session, child_id=child_id)


@app.get("/api/messages")
async def api_messages(since_days: int = 7) -> list[dict[str, Any]]:
    from datetime import datetime, timedelta, timezone as _tz
    async with get_async_session() as session:
        since = datetime.now(tz=_tz.utc) - timedelta(days=since_days)
        return await Q.get_messages(session, since=since)


@app.get("/api/notifications")
async def api_notifications(
    since_days: int = 7,
    child_id: int | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    from datetime import datetime, timedelta, timezone as _tz
    async with get_async_session() as session:
        since = datetime.now(tz=_tz.utc) - timedelta(days=since_days)
        return await Q.get_events(
            session, since=since, child_id=child_id, limit=limit
        )


@app.get("/api/attachments")
async def api_attachments_list(
    child_id: int | None = None,
    source_kind: str | None = None,
    limit: int = 200,
) -> list[dict[str, Any]]:
    async with get_async_session() as session:
        return await Q.list_attachments(
            session, child_id=child_id, source_kind=source_kind, limit=limit
        )


@app.get("/api/attachments/{attachment_id}")
async def api_attachment_download(attachment_id: int):
    from fastapi.responses import FileResponse
    from .config import REPO_ROOT
    from .util import paths as P
    async with get_async_session() as session:
        att = await Q.get_attachment_row(session, attachment_id)
    if att is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"attachment {attachment_id} not found")
    path = (REPO_ROOT / att.local_path).resolve()
    if not path.exists():
        raise HTTPException(status.HTTP_410_GONE, f"file vanished on disk: {att.local_path}")
    # Guard path traversal: file must live under the data directory
    try:
        path.relative_to(P.data_root().resolve())
    except ValueError:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "attachment path escapes storage root")
    return FileResponse(
        path=str(path),
        media_type=att.mime_type or "application/octet-stream",
        filename=att.filename,
    )


@app.get("/api/assignments")
async def api_assignments(
    child_id: int | None = None,
    subject: str | None = None,
    status: str | None = None,
    limit: int = 500,
) -> list[dict[str, Any]]:
    async with get_async_session() as session:
        return await Q.get_all_assignments(
            session, child_id=child_id, subject=subject, status=status, limit=limit
        )


@app.get("/api/comments")
async def api_comments(child_id: int | None = None, limit: int = 200) -> list[dict[str, Any]]:
    async with get_async_session() as session:
        return await Q.get_comments(session, child_id=child_id, limit=limit)


@app.get("/api/notes")
async def api_notes(child_id: int | None = None, limit: int = 200) -> list[dict[str, Any]]:
    async with get_async_session() as session:
        return await Q.get_notes(session, child_id=child_id, limit=limit)


@app.post("/api/notes")
async def api_notes_add(payload: dict[str, Any]) -> dict[str, Any]:
    note = (payload or {}).get("note")
    if not isinstance(note, str) or not note.strip():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "note is required")
    async with get_async_session() as session:
        return await Q.add_parent_note(
            session,
            text=note,
            child_id=(payload or {}).get("child_id"),
            tags=(payload or {}).get("tags"),
        )


@app.get("/api/summaries")
async def api_summaries(kind: str | None = None, limit: int = 60) -> list[dict[str, Any]]:
    async with get_async_session() as session:
        return await Q.get_summaries(session, kind=kind, limit=limit)


@app.get("/api/child/{child_id}")
async def api_child_detail(child_id: int) -> dict[str, Any]:
    async with get_async_session() as session:
        r = await Q.get_child_detail(session, child_id)
    if r is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"child {child_id} not found")
    return r


@app.get("/api/overdue-trend")
async def api_overdue_trend(
    child_id: int | None = None, days: int = 14
) -> list[dict[str, Any]]:
    async with get_async_session() as session:
        return await Q.get_overdue_trend(session, child_id=child_id, days=days)


@app.get("/api/shaky-topics")
async def api_shaky_topics(
    child_id: int | None = None,
    limit: int | None = None,
) -> list[dict[str, Any]] | dict[str, Any]:
    """Topics per kid that warrant a review conversation, ordered by
    shakiness. No cap by default — the parent sees the full list and
    dismisses items per-row to whittle down. Each item carries a
    `reasons` list so the parent knows why it surfaced."""
    from sqlalchemy import select
    from .models import Child
    from .services.shaky_topics import shaky_for_child, shaky_for_all
    async with get_async_session() as session:
        if child_id is None:
            return await shaky_for_all(session, limit_per_kid=limit)
        child = (
            await session.execute(select(Child).where(Child.id == child_id))
        ).scalar_one_or_none()
        if child is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, f"child {child_id} not found")
        return await shaky_for_child(session, child, limit=limit)


@app.get("/api/excellence")
async def api_excellence(child_id: int | None = None) -> list[dict[str, Any]] | dict[str, Any]:
    """Vasant Valley's Excellence-Award track (≥85 % overall yearly
    average for 5 consecutive years). Returns the current year's stats
    per kid: grades_count, above_85_count, current_year_avg, on_track.
    `below_85_recent` lists the 5 most-recent <85% items for drill-down."""
    from .services.excellence import status_for_all, status_for_child
    from sqlalchemy import select
    from .models import Child
    async with get_async_session() as session:
        if child_id is None:
            return await status_for_all(session)
        child = (
            await session.execute(select(Child).where(Child.id == child_id))
        ).scalar_one_or_none()
        if child is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, f"child {child_id} not found")
        return (await status_for_child(session, child)).to_dict()


@app.get("/api/topic-state")
async def api_topic_state(child_id: int) -> list[dict[str, Any]]:
    """Per-(subject × topic) mastery state for one kid. Driven by
    services.topic_state — Khan Academy heuristics + Cepeda decay
    over grades + assignments tagged to syllabus topics."""
    from .services.topic_state import list_topic_state
    async with get_async_session() as session:
        return await list_topic_state(session, child_id)


@app.post("/api/topic-state/recompute")
async def api_topic_state_recompute(child_id: int | None = None) -> dict[str, Any]:
    """Rebuild topic_state for one or all kids. Idempotent — wipes and
    re-derives. Heavy-tier sync runs this weekly; this endpoint is for
    on-demand refresh after a data import."""
    from .services.topic_state import recompute_for_child, recompute_all
    from sqlalchemy import select
    from .models import Child
    async with get_async_session() as session:
        if child_id is None:
            return await recompute_all(session)
        child = (
            await session.execute(select(Child).where(Child.id == child_id))
        ).scalar_one_or_none()
        if child is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, f"child {child_id} not found")
        return await recompute_for_child(session, child)


@app.post("/api/match-grades")
async def api_match_grades(
    child_id: int | None = None,
    use_llm: bool = True,
) -> dict[str, Any]:
    """Run the grade↔assignment matcher across every still-unlinked grade
    row. Two-pass: deterministic Jaccard + date proximity first; the local
    LLM (Ollama by default) acts as a tiebreaker only when the top two
    candidates are within a small confidence margin. Idempotent — strong
    existing links are kept."""
    from .services.grade_match import match_unlinked_grades
    async with get_async_session() as session:
        return await match_unlinked_grades(
            session, child_id=child_id, use_llm_tiebreaker=use_llm,
        )


@app.get("/api/submission-heatmap")
async def api_submission_heatmap(
    child_id: int | None = None, weeks: int = 14
) -> list[dict[str, Any]]:
    """Daily completion counts (due/closed/ratio) over the last N weeks.
    Drives the GitHub-style heatmap on per-kid pages."""
    async with get_async_session() as session:
        return await Q.get_submission_heatmap(session, child_id=child_id, weeks=weeks)


@app.get("/api/notification-snoozes")
async def api_notification_snoozes() -> list[dict[str, Any]]:
    """List active (un-expired) notification snoozes — one row per
    (rule_id, child_id) the parent has muted. Used by the (why?) popover
    to show a "currently snoozed until …" hint."""
    from datetime import datetime, timezone as _tz
    from sqlalchemy import select
    from .models import NotificationSnooze
    async with get_async_session() as session:
        rows = (
            await session.execute(
                select(NotificationSnooze)
                .where(NotificationSnooze.until > datetime.now(tz=_tz.utc))
                .order_by(NotificationSnooze.until.desc())
            )
        ).scalars().all()
    return [
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


@app.post("/api/notification-snoozes")
async def api_notification_snoozes_add(payload: dict[str, Any]) -> dict[str, Any]:
    """Snooze a (rule_id, child_id) until `until` (ISO datetime in UTC).
    Idempotent — the unique key (rule_id, child_id) is upserted; the
    new `until` replaces an older one."""
    from datetime import datetime, timezone as _tz
    from sqlalchemy import select
    from .models import NotificationSnooze
    rule_id = (payload or {}).get("rule_id")
    if not rule_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "rule_id required")
    child_id = (payload or {}).get("child_id")
    until_raw = (payload or {}).get("until")
    if until_raw is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "until required (ISO UTC)")
    try:
        until_dt = datetime.fromisoformat(str(until_raw).replace("Z", "+00:00"))
    except ValueError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"bad until: {until_raw}")
    if until_dt.tzinfo is None:
        until_dt = until_dt.replace(tzinfo=_tz.utc)
    reason = (payload or {}).get("reason")
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
    return {
        "id": row.id,
        "rule_id": row.rule_id,
        "child_id": row.child_id,
        "until": row.until.isoformat(),
        "reason": row.reason,
    }


@app.delete("/api/notification-snoozes/{snooze_id}")
async def api_notification_snoozes_delete(snooze_id: int) -> dict[str, Any]:
    """Cancel an active snooze by id. Returns ok=True even if already
    expired/missing — idempotent."""
    from sqlalchemy import delete
    from .models import NotificationSnooze
    async with get_async_session() as session:
        await session.execute(
            delete(NotificationSnooze).where(NotificationSnooze.id == snooze_id)
        )
        await session.commit()
    return {"ok": True, "id": snooze_id}


@app.get("/api/patterns")
async def api_patterns(child_id: int | None = None) -> dict[str, Any] | list[dict[str, Any]]:
    """Monthly behavioural patterns per kid: lateness, repeated_attempt,
    weekend_cramming. Each row carries a `detail` blob with supporting
    counts + example titles. Read-only — call POST /recompute to rebuild."""
    from sqlalchemy import select
    from .models import Child
    from .services.patterns import list_patterns, list_patterns_all
    async with get_async_session() as session:
        if child_id is None:
            return await list_patterns_all(session)
        child = (
            await session.execute(select(Child).where(Child.id == child_id))
        ).scalar_one_or_none()
        if child is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, f"child {child_id} not found")
        return await list_patterns(session, child_id)


@app.post("/api/patterns/recompute")
async def api_patterns_recompute(
    child_id: int | None = None, months: int = 6,
) -> dict[str, Any]:
    """Rebuild pattern_state rows for the last N months. Idempotent —
    deletes the existing rows for the same months and rewrites them."""
    from sqlalchemy import select
    from .models import Child
    from .services.patterns import compute_all, compute_for_child
    async with get_async_session() as session:
        if child_id is None:
            return await compute_all(session, months=months)
        child = (
            await session.execute(select(Child).where(Child.id == child_id))
        ).scalar_one_or_none()
        if child is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, f"child {child_id} not found")
        rows = await compute_for_child(session, child, months=months)
        return {"child_id": child_id, "rows": len(rows), "months": months}


@app.get("/api/homework-load")
async def api_homework_load(
    child_id: int | None = None,
    weeks: int = 8,
    extra_minutes_per_item: int | None = None,
) -> dict[str, Any] | list[dict[str, Any]]:
    """Per-week homework load with the CBSE policy cap drawn as a
    reference horizon. We can't measure real time-on-task — this is an
    estimate from assignment counts × per-class minutes-per-item. The
    response carries an explicit `honest_caveat` and `cap_basis` so the UI
    frames the cap as official policy, not a verdict on the school."""
    from sqlalchemy import select
    from .models import Child
    from .services.homework_load import homework_load, homework_load_all
    async with get_async_session() as session:
        if child_id is None:
            return {
                "kids": await homework_load_all(session, weeks=weeks),
                "weeks": weeks,
            }
        child = (
            await session.execute(select(Child).where(Child.id == child_id))
        ).scalar_one_or_none()
        if child is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, f"child {child_id} not found")
        return await homework_load(
            session,
            child,
            weeks=weeks,
            extra_minutes_per_item=extra_minutes_per_item,
        )


@app.get("/api/grade-trends/annotate")
async def api_grade_trends_annotate(child_id: int) -> list[dict[str, Any]]:
    from .services.annotations import annotate_grade_trends
    async with get_async_session() as session:
        return await annotate_grade_trends(session, child_id)


@app.post("/api/notifications/replay")
async def api_notifications_replay(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    from .services.replay import replay_notifications
    payload = payload or {}
    async with get_async_session() as session:
        return await replay_notifications(
            session,
            since_days=int(payload.get("since_days", 7)),
            child_id=payload.get("child_id"),
            limit=int(payload.get("limit", 200)),
        )


# ── Veracross credentials + sync health + remote-login ───────────────────────

@app.get("/api/veracross/credentials")
async def api_vc_credentials_get() -> dict[str, Any]:
    from .services.veracross_creds import public_view
    return public_view()


@app.put("/api/veracross/credentials")
async def api_vc_credentials_put(payload: dict[str, Any]) -> dict[str, Any]:
    from .services.veracross_creds import save_credentials
    return save_credentials(payload or {})


@app.get("/api/veracross/status")
async def api_vc_status() -> dict[str, Any]:
    from .services.sync_health import snapshot
    async with get_async_session() as session:
        return await snapshot(session)


@app.post("/api/veracross/auth-check")
async def api_vc_auth_check() -> dict[str, Any]:
    """Quick, cheap live probe: loads storage_state cookies and does one
    HTTPX GET to the portal to decide whether the session is currently
    valid. Way faster than spinning Playwright for a full sync."""
    from .services.auth_check import probe
    return await probe()


@app.post("/api/veracross/login/start")
async def api_vc_login_start() -> dict[str, Any]:
    from .services.remote_login import start_session
    return await start_session()


@app.get("/api/veracross/login/status")
async def api_vc_login_status() -> dict[str, Any]:
    from .services.remote_login import current_status
    return await current_status()


@app.get("/api/veracross/login/screenshot")
async def api_vc_login_screenshot():
    from fastapi.responses import Response
    from .services.remote_login import screenshot_png
    png = await screenshot_png()
    if not png:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no active session or screenshot yet")
    return Response(content=png, media_type="image/png", headers={
        "Cache-Control": "no-store",
    })


@app.post("/api/veracross/login/click")
async def api_vc_login_click(payload: dict[str, Any]) -> dict[str, Any]:
    from .services.remote_login import click
    return await click(
        int(payload.get("x", 0)),
        int(payload.get("y", 0)),
        button=str(payload.get("button", "left")),
    )


@app.post("/api/veracross/login/type")
async def api_vc_login_type(payload: dict[str, Any]) -> dict[str, Any]:
    from .services.remote_login import type_text
    return await type_text(str(payload.get("text", "")))


@app.post("/api/veracross/login/key")
async def api_vc_login_key(payload: dict[str, Any]) -> dict[str, Any]:
    from .services.remote_login import press_key
    return await press_key(str(payload.get("key", "")))


@app.post("/api/veracross/login/fill-credentials")
async def api_vc_login_fill() -> dict[str, Any]:
    from .services.remote_login import fill_credentials
    return await fill_credentials()


@app.get("/api/veracross/login/check-success")
async def api_vc_login_check() -> dict[str, Any]:
    from .services.remote_login import check_success
    return await check_success()


@app.post("/api/veracross/login/finish")
async def api_vc_login_finish() -> dict[str, Any]:
    from .services.remote_login import finish_and_save
    return await finish_and_save()


@app.delete("/api/veracross/login")
async def api_vc_login_close() -> dict[str, Any]:
    from .services.remote_login import close_session
    return await close_session()


@app.get("/api/ui-prefs")
async def api_ui_prefs_get() -> dict[str, Any]:
    """Returns the full UI-preferences blob: collapsed sections, bucket
    ordering, kid ordering, etc. Single-user app — no auth scoping."""
    from .services.ui_prefs import load_prefs
    return load_prefs()


@app.put("/api/ui-prefs")
async def api_ui_prefs_put(payload: dict[str, Any]) -> dict[str, Any]:
    """Merge-update the prefs blob and return the canonical result.
    If any sync-cron keys changed, re-register the APScheduler job
    so the new cadence takes effect immediately."""
    from .services.ui_prefs import save_prefs
    r = save_prefs(payload or {})
    sync_keys = {"sync_interval_hours", "sync_window_start_hour", "sync_window_end_hour"}
    if payload and any(k in payload for k in sync_keys):
        try:
            from .jobs.scheduler import reschedule_sync_job
            reschedule_sync_job()
        except Exception:
            pass
    return r


@app.post("/api/syllabus/check-now")
async def api_syllabus_check_now() -> dict[str, Any]:
    """Run the weekly syllabus recheck immediately — re-downloads + re-parses
    each class's syllabus, diffs against the stored JSON, persists a
    `syllabus_changed` event when anything differs."""
    from .jobs.syllabus_job import check_syllabus_updates
    return await check_syllabus_updates()


@app.get("/api/syllabus/{class_level}")
async def api_syllabus(class_level: int) -> dict[str, Any]:
    from .services.syllabus import merged_syllabus
    async with get_async_session() as session:
        return await merged_syllabus(session, class_level)


@app.put("/api/syllabus/{class_level}/cycle/{cycle_name}")
async def api_syllabus_cycle_put(
    class_level: int, cycle_name: str, payload: dict[str, Any]
) -> dict[str, Any]:
    from .services.syllabus import upsert_cycle_override
    async with get_async_session() as session:
        return await upsert_cycle_override(
            session,
            class_level=class_level,
            cycle_name=cycle_name,
            start=payload.get("start"),
            end=payload.get("end"),
            note=payload.get("note"),
        )


@app.put("/api/syllabus/{class_level}/topic")
async def api_syllabus_topic_put(
    class_level: int, payload: dict[str, Any]
) -> dict[str, Any]:
    from .services.syllabus import upsert_topic_status
    subj = payload.get("subject")
    topic = payload.get("topic")
    if not subj or not topic:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "subject and topic are required")
    try:
        return_ = None
        async with get_async_session() as session:
            return_ = await upsert_topic_status(
                session,
                class_level=class_level,
                subject=subj,
                topic=topic,
                status=payload.get("status"),
                note=payload.get("note"),
            )
        return return_
    except ValueError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e))


@app.patch("/api/assignments/{item_id}")
async def api_patch_assignment(item_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    """Partial update of parent-side state (any subset of parent_status,
    priority, snooze_until, status_notes, tags, note). Every changed field
    is logged to assignment_status_history."""
    from .services import assignment_state as ast
    async with get_async_session() as session:
        try:
            r = await ast.update_assignment_state(
                session, item_id, payload, actor=payload.get("actor"),
            )
        except ValueError as e:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e))
    if r is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"assignment {item_id} not found")
    return r


@app.get("/api/assignments/{item_id}/history")
async def api_assignment_history(item_id: int, limit: int = 200) -> list[dict[str, Any]]:
    from .services import assignment_state as ast
    async with get_async_session() as session:
        return await ast.get_history(session, item_id, limit=limit)


@app.post("/api/assignments/{item_id}/self-prediction")
async def api_set_self_prediction(
    item_id: int, payload: dict[str, Any],
) -> dict[str, Any]:
    """Set / clear the kid's self-prediction band for an assignment.
    `prediction` ∈ {'high','mid','low','%nn'} or None to clear.
    If a grade is already linked, the outcome is computed in-line so the
    UI gets the post-grade state on the same response."""
    from datetime import datetime, timezone as _tz
    from sqlalchemy import select
    from .models import VeracrossItem
    from .services import self_prediction as SP

    pred_raw = (payload or {}).get("prediction")
    if pred_raw is not None and not SP.is_valid_prediction(pred_raw):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "prediction must be one of high/mid/low or '%nn' (0..100)",
        )

    async with get_async_session() as session:
        item = (
            await session.execute(
                select(VeracrossItem).where(VeracrossItem.id == item_id)
            )
        ).scalar_one_or_none()
        if item is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, f"assignment {item_id} not found")

        if pred_raw is None:
            item.self_prediction = None
            item.self_prediction_set_at = None
            item.self_prediction_outcome = None
        else:
            item.self_prediction = pred_raw.strip().lower()
            item.self_prediction_set_at = datetime.now(tz=_tz.utc)
            # If a grade is already linked, compute outcome immediately.
            grade_pct = await _grade_pct_for_assignment(session, item.id)
            item.self_prediction_outcome = SP.outcome_for(
                item.self_prediction, grade_pct,
            )
        await session.commit()
        await session.refresh(item)

    return {
        "item_id": item.id,
        "self_prediction": item.self_prediction,
        "self_prediction_set_at": (
            item.self_prediction_set_at.isoformat()
            if item.self_prediction_set_at else None
        ),
        "self_prediction_outcome": item.self_prediction_outcome,
    }


async def _grade_pct_for_assignment(session, assignment_id: int) -> float | None:
    """Look up the most recent grade percentage linked to this assignment.
    Returns None if no grade has been matched yet."""
    import json
    from sqlalchemy import select
    from .models import VeracrossItem
    rows = (
        await session.execute(
            select(VeracrossItem)
            .where(VeracrossItem.kind == "grade")
            .where(VeracrossItem.linked_assignment_id == assignment_id)
            .order_by(VeracrossItem.due_or_date.desc())
        )
    ).scalars().all()
    for r in rows:
        try:
            n = json.loads(r.normalized_json or "{}")
            pct = n.get("grade_pct")
            if pct is not None:
                return float(pct)
        except Exception:
            continue
    return None


@app.get("/api/sentiment-trend")
async def api_sentiment_trend(
    child_id: int | None = None,
    window_days: int = 28,
    bucket_days: int = 7,
) -> dict[str, Any]:
    """Rolling sentiment trend across the last N days of teacher comments.

    Honest framing: an offline lexicon classifier (services/sentiment.py)
    runs over each comment's text — no LLM, no remote calls. We surface
    the *trend* (per-week mean), never a raw score, never a single
    comment. The pedagogy synthesis flagged this: per-comment sentiment
    is noisy by nature; aggregating by week and showing the direction
    is the responsible disclosure.

    Returns:
      points  — list of {bucket_start, n, mean_score} (n=0 when the
                bucket had no comments; mean_score=None then)
      total_comments  — total comments in the window
      direction        — "rising" | "falling" | "flat" | None
                         derived from the slope of mean_scores
    """
    from datetime import datetime, timezone as _tz, timedelta
    from sqlalchemy import select
    from .models import VeracrossItem
    from .services.sentiment import trend_points
    from .services.grade_match import _parse_loose_date

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
    # Direction = sign of (last non-null point − first non-null point).
    means = [p["mean_score"] for p in points if p.get("mean_score") is not None]
    direction: str | None = None
    if len(means) >= 2:
        delta = means[-1] - means[0]  # type: ignore
        if delta > 0.15:
            direction = "rising"
        elif delta < -0.15:
            direction = "falling"
        else:
            direction = "flat"

    return {
        "points": points,
        "total_comments": len(items),
        "window_days": window_days,
        "bucket_days": bucket_days,
        "direction": direction,
        "honest_caveat": (
            "Per-comment sentiment is noisy; we surface only the rolling "
            "trend across the window. Empty buckets are gaps, not zeros."
        ),
    }


@app.get("/api/self-prediction/calibration")
async def api_self_prediction_calibration(
    child_id: int | None = None,
) -> dict[str, Any]:
    """Aggregate calibration: how often did the kid's predictions match,
    overshoot, undershoot? Returns counts + share_matched + the recent
    rows so the UI can render a sparkline and a list."""
    from sqlalchemy import select
    from .models import VeracrossItem
    from .services import self_prediction as SP
    async with get_async_session() as session:
        q = (
            select(VeracrossItem)
            .where(VeracrossItem.kind == "assignment")
            .where(VeracrossItem.self_prediction.isnot(None))
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
    return {
        "summary": SP.calibration_summary(rows),
        "rows": rows,
    }


@app.get("/api/assignments/constants")
async def api_assignment_constants() -> dict[str, Any]:
    """Surface the fixed enums (parent-statuses + tag vocabulary) to the
    frontend so the popover UI and the backend stay in sync."""
    from .services import assignment_state as ast
    return {
        "parent_statuses": list(ast.PARENT_STATUSES),
        "fixed_tags": list(ast.FIXED_TAGS),
    }


@app.post("/api/assignments/{item_id}/mark-submitted")
async def api_mark_submitted(item_id: int) -> dict[str, Any]:
    """Parent-side submitted flag — used when the teacher hasn't updated the portal yet."""
    async with get_async_session() as session:
        r = await Q.mark_assignment_submitted(session, item_id, submitted=True)
    if r.get("status") == "not_found":
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"assignment {item_id} not found")
    return r


@app.delete("/api/assignments/{item_id}/mark-submitted")
async def api_unmark_submitted(item_id: int) -> dict[str, Any]:
    """Clear the parent-side submitted override."""
    async with get_async_session() as session:
        r = await Q.mark_assignment_submitted(session, item_id, submitted=False)
    if r.get("status") == "not_found":
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"assignment {item_id} not found")
    return r


@app.post("/api/sync")
async def api_sync(background: BackgroundTasks) -> dict[str, Any]:
    """Kick off a sync in the background; return immediately."""
    background.add_task(run_sync, "api")
    return {"status": "queued", "trigger": "api"}


@app.post("/api/sync-blocking")
async def api_sync_blocking() -> dict[str, Any]:
    """Run a sync inline and return its result. Useful for manual runs/tests."""
    return await run_sync(trigger="api-blocking")


@app.get("/api/sync-runs")
async def api_sync_runs(limit: int = 60) -> list[dict[str, Any]]:
    from sqlalchemy import desc, select, func as _func
    from .models import SyncRun
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
        return [
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
                "log_length": int(r.log_length or 0),
            }
            for r in rows
        ]


@app.get("/api/sync-runs/{run_id}/log")
async def api_sync_run_log(run_id: int) -> dict[str, Any]:
    """Full captured log text for one sync run. Logs are retained for 7
    days; rows older than that are purged by the daily retention job.

    Also returns `log_capture_healthy`: True iff the start + end sentinels
    are present in the log text — a quick way for the UI to flag runs where
    the logging handler was misconfigured or detached prematurely."""
    from sqlalchemy import select
    from .models import SyncRun
    async with get_async_session() as session:
        r = (
            await session.execute(
                select(SyncRun).where(SyncRun.id == run_id)
            )
        ).scalar_one_or_none()
    if r is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"sync run {run_id} not found")
    log_text = r.log_text or ""
    has_start = "=== sync started" in log_text
    has_end = "=== sync ended" in log_text
    is_running = r.status == "running"
    log_capture_healthy = (
        is_running and has_start
    ) or (not is_running and has_start and has_end)
    lines = log_text.splitlines()
    return {
        "id": r.id,
        "started_at": r.started_at.isoformat() if r.started_at else None,
        "ended_at": r.ended_at.isoformat() if r.ended_at else None,
        "trigger": r.trigger,
        "status": r.status,
        "error": r.error,
        "log_text": log_text,
        "log_line_count": len(lines),
        "log_capture_healthy": log_capture_healthy,
        "has_start_sentinel": has_start,
        "has_end_sentinel": has_end,
    }


@app.get("/api/sync-runs/concurrency-check")
async def api_sync_concurrency_check() -> dict[str, Any]:
    """Returns info about currently-running sync(s). If more than one row
    is at status='running', something is wrong — the UI can warn."""
    from sqlalchemy import select, desc
    from .models import SyncRun
    async with get_async_session() as session:
        running = (
            await session.execute(
                select(SyncRun).where(SyncRun.status == "running").order_by(desc(SyncRun.started_at))
            )
        ).scalars().all()
    from datetime import datetime, timezone
    now = datetime.now(tz=timezone.utc)
    return {
        "count": len(running),
        "multiple_running": len(running) > 1,
        "runs": [
            {
                "id": r.id,
                "started_at": r.started_at.isoformat() if r.started_at else None,
                "age_sec": int((now - r.started_at).total_seconds()) if r.started_at else None,
                "trigger": r.trigger,
                "stale": r.started_at and (now - r.started_at).total_seconds() > 15 * 60,
            }
            for r in running
        ],
    }


@app.post("/api/sync-runs/prune")
async def api_sync_runs_prune(days: int = 7) -> dict[str, Any]:
    """Manual retention trigger — same as the daily job but on demand."""
    from .jobs.retention_job import prune_sync_logs
    return await prune_sync_logs(days=days)


@app.get("/api/channel-config")
async def api_get_channel_config() -> dict[str, Any]:
    async with get_async_session() as session:
        return await load_config(session)


@app.put("/api/channel-config")
async def api_put_channel_config(config: dict[str, Any]) -> dict[str, Any]:
    async with get_async_session() as session:
        await save_config(session, config)
    return {"status": "ok"}


@app.post("/api/channels/{channel}/test")
async def api_channel_test(channel: str, message: str = "Hello from Parent Cockpit") -> dict[str, Any]:
    from .channels.email import EmailChannel
    from .channels.inapp import InAppChannel
    from .channels.telegram import TelegramChannel
    channels = {
        "telegram": TelegramChannel,
        "email": EmailChannel,
        "inapp": InAppChannel,
    }
    cls = channels.get(channel)
    if cls is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"unknown channel: {channel}")
    r = await cls().send_test(message)
    return {"channel": r.channel, "status": r.status, "error": r.error}


@app.post("/api/digest/run")
async def api_digest_run(background: BackgroundTasks, kind: str = "digest_4pm") -> dict[str, Any]:
    from .jobs.digest_job import run_daily_digest, run_weekly_digest
    if kind == "digest_4pm":
        background.add_task(run_daily_digest)
    elif kind == "weekly":
        background.add_task(run_weekly_digest)
    else:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"unknown kind: {kind}")
    return {"status": "queued", "kind": kind}


@app.get("/api/digest")
async def api_digest_get(date_iso: str | None = None) -> dict[str, Any]:
    async with get_async_session() as session:
        row = await Q.get_digest_summary(
            session,
            d=None if date_iso is None else __import__("datetime").date.fromisoformat(date_iso),
        )
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no digest for that date")
    return row


@app.get("/api/digest/preview")
async def api_digest_preview() -> dict[str, Any]:
    """Build-and-render a digest without persisting or dispatching. Cheap preview."""
    data = await generate_and_store_digest(kind="digest_preview", llm=False)
    return render_for_digest(data)


async def _resolve_child(session: Any, child_id: int):
    from sqlalchemy import select
    from .models import Child
    child = (
        await session.execute(select(Child).where(Child.id == child_id))
    ).scalar_one_or_none()
    if child is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"child {child_id} not found")
    return child


@app.get("/api/spellbee/lists")
async def api_spellbee_lists(child_id: int) -> list[dict[str, Any]]:
    """Directory listing of Spelling Bee word lists for one child. Files
    live under data/rawdata/<kid_slug>/spellbee/."""
    from .services import spellbee as SB
    async with get_async_session() as session:
        child = await _resolve_child(session, child_id)
    return [x.to_dict() for x in SB.list_lists(child)]


@app.get("/api/spellbee/list/{child_id}/{filename}")
async def api_spellbee_download(child_id: int, filename: str):
    from fastapi.responses import FileResponse
    from .services import spellbee as SB
    async with get_async_session() as session:
        child = await _resolve_child(session, child_id)
    path = SB.resolve_file(child, filename)
    if path is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"spellbee list {filename!r} not found")
    ext = path.suffix.lower()
    mime = SB._MIME_BY_EXT.get(ext, "application/octet-stream")
    return FileResponse(path=str(path), media_type=mime, filename=path.name)


@app.get("/api/school-messages/grouped")
async def api_school_messages_grouped(limit: int = 50) -> list[dict[str, Any]]:
    """School messages collapsed by normalized title. Each group includes
    every kid the announcement was tagged for + cached llm_summary if a
    parent has clicked Summarize on the row."""
    from .services.school_messages import list_grouped_messages
    async with get_async_session() as session:
        return await list_grouped_messages(session, limit=limit)


@app.post("/api/school-messages/{group_id}/summarize")
async def api_school_messages_summarize(group_id: str) -> dict[str, Any]:
    """Generate (or refresh) the 1-sentence summary for a dedup group
    via local Ollama. Result is cached on every member row's
    llm_summary / llm_summary_url so subsequent calls / page loads
    don't re-call the LLM."""
    from .services.school_messages import summarize_group
    async with get_async_session() as session:
        try:
            return await summarize_group(session, group_id)
        except ValueError as e:
            raise HTTPException(status.HTTP_404_NOT_FOUND, str(e))


@app.get("/api/portfolio")
async def api_portfolio_list(
    child_id: int | None = None,
    subject: str | None = None,
    topic: str | None = None,
) -> list[dict[str, Any]]:
    """List portfolio attachments for a kid / subject / topic. Returns
    metadata only — clients fetch the actual file bytes via
    /api/attachments/{attachment_id} (which gates by source_kind to
    prevent path-traversal)."""
    from .services.portfolio import list_portfolio
    async with get_async_session() as session:
        return await list_portfolio(
            session, child_id=child_id, subject=subject, topic=topic,
        )


@app.post("/api/portfolio/upload")
async def api_portfolio_upload(
    child_id: int,
    subject: str,
    topic: str,
    files: list[UploadFile] = File(...),  # noqa: B008
    note: str | None = None,
) -> dict[str, Any]:
    """Upload one or more portfolio files (images / PDFs) tagged to a
    syllabus topic. Bound by natural key (subject, topic) so it survives
    nightly topic_state recomputes. SHA-256 dedup; 10 MB per-file cap."""
    from .services.portfolio import save_portfolio_upload
    async with get_async_session() as session:
        child = await _resolve_child(session, child_id)
        saved: list[dict[str, Any]] = []
        errors: list[dict[str, str]] = []
        for f in files:
            try:
                data = await f.read()
                row = await save_portfolio_upload(
                    session, child, subject, topic, f.filename or "unnamed",
                    data, note=note,
                )
                saved.append({
                    "id": row.id,
                    "filename": row.filename,
                    "mime_type": row.mime_type,
                    "size_bytes": row.size_bytes,
                    "uploaded_at": row.downloaded_at.isoformat() if row.downloaded_at else None,
                })
            except ValueError as e:
                errors.append({"filename": f.filename or "", "error": str(e)})
        await session.commit()
    return {"saved": saved, "errors": errors}


@app.delete("/api/portfolio/{attachment_id}")
async def api_portfolio_delete(attachment_id: int) -> dict[str, Any]:
    """Remove a portfolio row + its file. No-ops on non-portfolio rows."""
    from .services.portfolio import delete_portfolio
    async with get_async_session() as session:
        ok = await delete_portfolio(session, attachment_id)
        if ok:
            await session.commit()
    if not ok:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "portfolio attachment not found")
    return {"ok": True, "id": attachment_id}


@app.post("/api/spellbee/upload")
async def api_spellbee_upload(
    child_id: int,
    files: list[UploadFile] = File(...),  # noqa: B008
) -> dict[str, Any]:
    """Upload one or more Spelling Bee list files for a child. Writes under
    data/rawdata/<kid_slug>/spellbee/. Overwrites any file with the same
    sanitized name."""
    from .services import spellbee as SB
    async with get_async_session() as session:
        child = await _resolve_child(session, child_id)
    saved: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    for f in files:
        try:
            data = await f.read()
            row = SB.save_upload(child, f.filename or "unnamed", data)
            saved.append(row.to_dict())
        except ValueError as e:
            errors.append({"filename": f.filename or "", "error": str(e)})
    return {"saved": saved, "errors": errors}


@app.delete("/api/spellbee/list/{child_id}/{filename}")
async def api_spellbee_delete(child_id: int, filename: str) -> dict[str, Any]:
    from .services import spellbee as SB
    async with get_async_session() as session:
        child = await _resolve_child(session, child_id)
    if not SB.delete_file(child, filename):
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"spellbee list {filename!r} not found")
    return {"status": "deleted", "filename": filename}


@app.post("/api/spellbee/list/{child_id}/{filename}/rename")
async def api_spellbee_rename(
    child_id: int, filename: str, payload: dict[str, Any],
) -> dict[str, Any]:
    from .services import spellbee as SB
    async with get_async_session() as session:
        child = await _resolve_child(session, child_id)
    new_name = (payload or {}).get("new_name") or ""
    if not new_name:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "new_name required")
    try:
        row = SB.rename_file(child, filename, new_name)
    except ValueError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e))
    return row.to_dict()


@app.get("/api/spellbee/linked-assignments")
async def api_spellbee_linked_assignments(child_id: int | None = None) -> list[dict[str, Any]]:
    """Assignments whose title/body/notes reference the Spelling Bee, with
    the detected list number and the matching file (if uploaded for that
    kid). `child_id` optional — filter to one child."""
    from sqlalchemy import select, desc
    from .models import VeracrossItem, Child
    from .services import spellbee as SB
    import json as _json
    out: list[dict[str, Any]] = []
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
        # Cache per-kid lists so we don't rescan the directory for every row
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
            out.append({
                "id": item.id,
                "child_id": child.id,
                "child_name": child.display_name,
                "subject": item.subject,
                "title": item.title,
                "title_en": item.title_en,
                "due_or_date": item.due_or_date,
                "status": item.status,
                "detected_list_number": num,
                "matched_list": match.to_dict() if match else None,
            })
    return out


@app.get("/api/resources")
async def api_resources(child_id: int | None = None) -> dict[str, Any]:
    """List every file under data/rawdata/, grouped by scope + category.
    If child_id is set, only that kid's per-kid resources are returned
    (schoolwide is always included). Used by the /resources UI page."""
    from sqlalchemy import select
    from .models import Child
    from .services import resources_index as RI
    async with get_async_session() as session:
        q = select(Child).order_by(Child.id)
        if child_id is not None:
            q = q.where(Child.id == child_id)
        children = list((await session.execute(q)).scalars().all())
    return RI.list_everything(children)


@app.get("/api/resources/file/schoolwide/{category}/{filename}")
async def api_resources_file_schoolwide(category: str, filename: str):
    from fastapi.responses import FileResponse
    from .services import resources_index as RI
    path = RI.resolve_schoolwide(category, filename)
    if path is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"resource not found")
    return FileResponse(path=str(path), media_type=RI._mime(path), filename=path.name)


@app.get("/api/resources/file/kid/{child_id}/{category}/{filename}")
async def api_resources_file_kid(child_id: int, category: str, filename: str):
    from fastapi.responses import FileResponse
    from sqlalchemy import select
    from .models import Child
    from .services import resources_index as RI
    async with get_async_session() as session:
        child = (
            await session.execute(select(Child).where(Child.id == child_id))
        ).scalar_one_or_none()
    if child is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"child {child_id} not found")
    path = RI.resolve_kid(child, category, filename)
    if path is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"resource not found")
    return FileResponse(path=str(path), media_type=RI._mime(path), filename=path.name)


@app.get("/api/mcp-activity")
async def api_mcp_activity(limit: int = 50) -> list[dict[str, Any]]:
    """Recent MCP tool-call audit entries (for the /notifications UI tab)."""
    from sqlalchemy import desc, select
    from .models import MCPToolCall
    async with get_async_session() as session:
        rows = (
            await session.execute(
                select(MCPToolCall).order_by(desc(MCPToolCall.created_at)).limit(limit)
            )
        ).scalars().all()
        return [
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


# ─── mount MCP transports ─────────────────────────────────────────────────────
# Streamable-HTTP (preferred) at /mcp, SSE (compat) at /mcp/sse.

app.mount(
    "/mcp",
    mcp_server.streamable_http_app(),
)

app.mount(
    "/mcp-sse",
    mcp_server.sse_app(),
)


def run() -> None:
    """Entry point for `schoolwork-api`. Uvicorn reload mode in dev."""
    import uvicorn

    uvicorn.run(
        "backend.app.main:app",
        host=settings.app_host,
        port=settings.app_port,
        reload=False,
        log_level=settings.log_level.lower(),
    )


if __name__ == "__main__":
    run()
