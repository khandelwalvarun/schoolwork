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

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Header, status
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

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):  # noqa: ANN001
    # MCP server's session_manager must run its own lifespan (for streamable-http).
    async with mcp_server.session_manager.run():
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
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
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
async def api_sync_runs(limit: int = 20) -> list[dict[str, Any]]:
    from sqlalchemy import desc, select
    from .models import SyncRun
    async with get_async_session() as session:
        rows = (
            await session.execute(
                select(SyncRun).order_by(desc(SyncRun.started_at)).limit(limit)
            )
        ).scalars().all()
        return [
            {
                "id": r.id,
                "started_at": r.started_at.isoformat() if r.started_at else None,
                "ended_at": r.ended_at.isoformat() if r.ended_at else None,
                "trigger": r.trigger,
                "status": r.status,
                "items_new": r.items_new,
                "items_updated": r.items_updated,
                "error": r.error,
            }
            for r in rows
        ]


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
