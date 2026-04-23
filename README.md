# schoolwork — Parent Cockpit for Vasant Valley / Veracross

Parent-facing tracker that ingests the Veracross portal hourly, computes a notability-scored event stream, and delivers a 4 pm digest across Telegram, email, and an in-app view. An MCP server sits alongside so Claude Dispatch, OpenClaw, and Claude Desktop can query the same data on demand — including free-form "ask a question" over unstructured content.

**Canonical plan:** [docs/BUILDSPEC.md](docs/BUILDSPEC.md).
**MCP layer:** [docs/BUILDSPEC_ADDENDUM_MCP.md](docs/BUILDSPEC_ADDENDUM_MCP.md), [docs/MCP.md](docs/MCP.md).

## Status

- ✅ Recon: 1559 pages crawled; portal structure fully mapped; component JSON APIs harvested.
- ✅ Schema: 10-table SQLite (WAL) + FTS5 search index, Alembic migration `0001`.
- ✅ **Scraper**: Playwright session-reuse, hybrid JSON + HTML parsing, planner-page extraction at `portals-embed.veracross.eu`, assignment/message detail enrichment. Rate-limited 3–6 s jittered. Re-login-on-session-expiry.
- ✅ **Notability engine**: rubric from BUILDSPEC §5.2, per-kind scoring, dedup, aggregate signals (`subject_concentration`, `backlog_accelerating`), persistence, dispatcher.
- ✅ **Channels**: Telegram bot, SMTP email, in-app; per-channel threshold + mute-list + quiet hours + rate limit; test-message endpoints.
- ✅ **APScheduler** in-process: hourly sync (08:00–22:00 IST), daily digest (16:00 IST), weekly digest (Sun 20:00 IST).
- ✅ **LLM client**: Anthropic SDK wrapper with cost tracking (INR) and `llm_calls` audit. Used for the digest preamble when `ANTHROPIC_API_KEY` is set.
- ✅ **Digest**: three renders from one `DigestData` (plain text/Telegram-markdown, email HTML, in-app HTML); matches the Cowork digest shape.
- ✅ **HTML Today view** served at `/` — no Node required.
- ✅ **MCP server**: 16 tools (read + write + search + digest + channels). Stdio + streamable-HTTP + SSE transports.
- ⏳ Syllabus parsing, grade trends + sparklines, React frontend — remaining W3/W4 polish.

## Quick start

```bash
uv sync
uv run playwright install chromium
uv run alembic upgrade head

# Configure .env from .env.example:
#   VERACROSS_USERNAME / VERACROSS_PASSWORD  (required)
#   ANTHROPIC_API_KEY                         (required for LLM digest preamble)
#   TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_IDS    (optional; no-op if absent)
#   SMTP_HOST / SMTP_USER / SMTP_PASSWORD / EMAIL_TO  (optional; no-op if absent)

# Seed the children table from the recon snapshot (one-time):
uv run python backend/scripts/seed_children.py

# Run one sync right now (populates veracross_items + events):
uv run python -m backend.app.scraper.sync

# Start API + MCP + scheduler:
uv run schoolwork-api          # -> http://127.0.0.1:8000/
# Browser the live Today view:  http://127.0.0.1:8000/
# API docs:                     http://127.0.0.1:8000/docs

# Stdio MCP for Claude Desktop / Code:
uv run schoolwork-mcp
```

## HTTP surface

| Path | Purpose |
|---|---|
| `/` | Live Today view (HTML) |
| `/health` | liveness + last_sync snapshot |
| `GET /api/children` | kids + class sections |
| `GET /api/today` | full Today JSON (per-kid overdue/due/upcoming + messages) |
| `GET /api/overdue`, `/api/due-today`, `/api/upcoming`, `/api/messages` | filtered lists |
| `GET /api/notifications` | events + per-channel delivery status |
| `GET /api/mcp-activity` | recent MCP tool-call audit |
| `GET /api/sync-runs` | sync history |
| `POST /api/sync` | queue a background sync |
| `POST /api/sync-blocking` | run a sync inline and return summary |
| `GET /api/channel-config`, `PUT /api/channel-config` | notification policy |
| `POST /api/channels/{channel}/test` | send test message |
| `GET /api/digest/preview` | build+render digest without dispatch |
| `POST /api/digest/run` | dispatch digest to all configured channels |
| `GET /api/digest?date_iso=YYYY-MM-DD` | cached digest for a past date |
| `POST /mcp` | MCP over streamable HTTP (Dispatch / OpenClaw) |
| `GET /mcp-sse` | MCP over SSE (legacy clients) |

## MCP tools (16)

Read: `list_children`, `get_today`, `get_overdue`, `get_due_today`, `get_upcoming`, `get_messages`, `get_notifications`, `get_digest`, `get_digest_preview`, `get_channel_config`, `ask`.

Write: `add_note`, `update_channel_config`, `test_channel`, `send_digest`, `trigger_sync`.

See [docs/MCP.md](docs/MCP.md) for wiring Dispatch / OpenClaw / Claude Desktop.

## Scheduler jobs

| Job | Schedule (IST) | What it does |
|---|---|---|
| `hourly_sync` | h=8–22 at :05 | Scrape planner + messages; produce events; dispatch high-notability ones. |
| `daily_digest` | 16:00 | Build digest, render 3 ways, send to all channels in `channels.digest.delivery`. |
| `weekly_digest` | Sun 20:00 | Same, weekly variant. |

## Layout

```
backend/app/
  main.py              FastAPI (mounts MCP, starts APScheduler)
  config.py            env-backed settings
  db.py                SQLAlchemy async + sync engines (SQLite WAL + FK on)
  models/              10 tables + FTS5 (migration 0001)
  scraper/
    client.py          Playwright session mgmt (login, re-login, rate-limit)
    parsers.py         pure HTML parsers
    sync.py            orchestrator: planner + messages → DB, produces events, dispatches
  notability/
    rubric.py          event kinds + notability scores (v1 per BUILDSPEC §5.2)
    engine.py          diff → events; subject_concentration; backlog_accelerating
    dispatcher.py      channel policy, dedup, per-channel rate limit, quiet hours
  channels/            base / telegram / email / inapp
  llm/                 anthropic wrapper + prompts/digest_preamble.md
  services/
    queries.py         shared read layer
    briefing.py        DigestData + generate_and_store_digest
    render.py          3 renderers (text, html, telegram)
  jobs/                scheduler + sync_job + digest_job
  mcp/server.py        16 tools (read/write/search/digest/channels)
scripts/               recon tooling (one-off): recon.py, harvest_components.py, build_sitemap.py
backend/scripts/       app-side utilities: seed_children.py
recon/                 captured HTML / screenshots / XHR / harvested API bodies
docs/                  BUILDSPEC, addendum, MCP
```

## Ground truth

Current sync against the live portal produces 30 assignments (Tejas 16 + Samarth 14) + 20 school messages. Totals match the reference Cowork digest (±1, accounting for the day passed). Event engine currently emits: 9 × `overdue_3d`, 2 × `overdue_7d`, 2 × `subject_concentration` (Maths for both kids), 2 × `backlog_accelerating`.

## Recon output

`recon/output/` contains the snapshot of the portal's structure captured on 2026-04-22:

- `manifest.json` — every captured page with URL, title, status.
- `pages/*.html` — rendered HTML per page.
- `screenshots/*.png` — full-page PNGs.
- `network/*.json` — every XHR/fetch request.
- `api/*.json` — harvested component JSON bodies.
- `embed/*.html` — planner pages per child (the real assignment data).
- `REPORT.md` — URL pattern inventory + API-surface map.
