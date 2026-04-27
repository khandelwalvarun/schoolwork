# MCP server — Dispatch / OpenClaw / Claude Desktop wiring

> 97 tools across 14 domains, all backed by the same SQLite + FastAPI codebase.
> See `docs/BUILDSPEC_ADDENDUM_MCP.md` for the original rationale.

## Transports

| Transport           | Endpoint                                      | Clients                                     |
| ------------------- | --------------------------------------------- | ------------------------------------------- |
| **stdio**           | `schoolwork-mcp` (installed as console script) | Claude Desktop, Claude Code local           |
| **Streamable HTTP** | `http://<host>/mcp`                            | Dispatch, OpenClaw, any modern HTTP client  |
| **SSE (legacy)**    | `http://<host>/mcp-sse`                        | Older MCP clients that require SSE          |

All three share the same tool implementations (`backend/app/mcp/server.py`) and the same SQLite DB. Switching transports is purely a client decision — no server change.

## Auth

- **stdio:** none — local trusted process.
- **HTTP / SSE:** bearer token enforced by an ASGI middleware (`mcp_bearer_middleware` in `backend/app/main.py`) that gates `/mcp*` and `/mcp-sse*` paths. Set `MCP_BEARER_TOKEN` in `.env` once the host is reachable off-LAN; until then, requests pass through unchallenged (dev mode).

### Generate a token

```bash
# Cryptographically secure 256-bit random token, base64.
python -c "import secrets; print(secrets.token_urlsafe(32))"

# Or:
openssl rand -hex 32
```

Then in `.env`:

```bash
MCP_BEARER_TOKEN=<the-token-you-just-generated>
```

Restart `schoolwork-api`. `/health` reports `mcp_auth_required: true` once the gate is on.

### Verify the gate

```bash
# 401 expected when token is set but missing/wrong:
curl -i -X POST http://localhost:7778/mcp \
     -H 'Accept: application/json, text/event-stream' \
     -H 'Content-Type: application/json' \
     -d '{"jsonrpc":"2.0","method":"tools/list","id":1}'
# → HTTP/1.1 401 Unauthorized
# → {"error":"Missing bearer token","hint":"Authorization: Bearer <token>"}

# 200 (or proper MCP response) once header is present:
curl -X POST http://localhost:7778/mcp \
     -H 'Accept: application/json, text/event-stream' \
     -H 'Content-Type: application/json' \
     -H "Authorization: Bearer $MCP_BEARER_TOKEN" \
     -d '{"jsonrpc":"2.0","method":"initialize","id":1,
          "params":{"protocolVersion":"2024-11-05","capabilities":{},
                    "clientInfo":{"name":"curl","version":"0"}}}'
```

## Tool surface

Every tool returns plain JSON (lists / dicts) and is logged to `mcp_tool_calls`. Errors raise — the caller sees `{ error: "<repr>" }`.

### Discovery

| Tool                      | Args                            | Returns                                                |
| ------------------------- | ------------------------------- | ------------------------------------------------------ |
| `list_children`           | —                               | `[{id, display_name, class_level, class_section, …}]`  |
| `get_today`               | —                               | `{generated_at, totals, children[], messages_last_7d[], last_sync}` |
| `get_child_detail`        | `child_id`                      | overdue/due_today/upcoming + grade trends + syllabus cycle + counts |
| `get_assignment_constants`| —                               | `{parent_statuses, fixed_tags}` — call before `update_assignment` |

### Backlog

| Tool               | Args                                                          | Returns        |
| ------------------ | ------------------------------------------------------------- | -------------- |
| `get_overdue`      | `child_id?`                                                   | `[Assignment]` |
| `get_due_today`    | `child_id?`                                                   | `[Assignment]` |
| `get_upcoming`     | `child_id?, days=14`                                          | `[Assignment]` |
| `list_assignments` | `child_id?, subject?, status?, limit=500`                     | `[Assignment]` |
| `get_overdue_trend`| `child_id?, days=14`                                          | `[{date, count}]` |

### Daily / Today / Briefs (Claude-driven)

| Tool                  | Args                                  | Returns                              |
| --------------------- | ------------------------------------- | ------------------------------------ |
| `get_daily_brief`     | `child_id?, refresh=false`            | per-kid 1-paragraph synthesis        |
| `get_sunday_brief`    | `child_id?, refresh=false`            | 4-section: cycle / one ask / teacher asks / what to ignore |
| `get_ptm_brief`       | `child_id, refresh=false`             | per-subject parent-teacher meeting prep, including parent's "worth a chat" list |

Both Sunday and PTM briefs are pre-warmed nightly at 02:00 IST and cached on disk under `data/cached_briefs/`. `refresh=true` skips the cache and re-runs Claude live (~30-60s).

### Grades + anomalies + sentiment

| Tool                       | Args                          | Returns                              |
| -------------------------- | ----------------------------- | ------------------------------------ |
| `get_grades`               | `child_id, subject?`          | every grade row                       |
| `get_grade_trends`         | `child_id`                    | per-subject mean / stddev / sparkline |
| `annotate_grade_trends`    | `child_id`                    | grade_trends + LLM commentary         |
| `get_anomalies`            | `child_id?`                   | off-trend grades                      |
| `explain_grade_anomaly`    | `grade_id, force=false`       | Claude hypothesis (cached)            |
| `get_sentiment_trend`      | `child_id?, window_days=28, bucket_days=7` | rolling lexicon-based trend         |
| `get_submission_heatmap`   | `child_id?, weeks=14`         | per-week × per-day-of-week status     |

### Topic mastery / syllabus

| Tool                          | Args                                       | Returns                              |
| ----------------------------- | ------------------------------------------ | ------------------------------------ |
| `get_topic_state`             | `child_id`                                 | per-(subject × topic) mastery        |
| `get_topic_detail`            | `child_id, subject, topic`                 | mastery + linked grades + assignments + portfolio |
| `get_shaky_topics`            | `limit=3`                                  | top decaying / shaky topics per kid  |
| `get_excellence_status`       | `child_id?`                                | Excellence-track arithmetic          |
| `recompute_topic_state`       | `child_id?`                                | trigger nightly recompute            |
| `match_grades_to_assignments` | `child_id?`                                | trigger nightly grade ↔ assignment matching |
| `get_syllabus`                | `class_level`                              | full syllabus cycle list             |
| `set_syllabus_cycle_override` | `class_level, cycle_name, start?, end?, note?` | override one cycle's dates       |
| `set_syllabus_topic_status`   | `class_level, subject, topic, status?, note?` | mark covered / skipped / etc.    |
| `trigger_syllabus_check`      | —                                          | run weekly syllabus recheck          |

### Patterns & load

| Tool                   | Args                                  | Returns                              |
| ---------------------- | ------------------------------------- | ------------------------------------ |
| `get_patterns`         | `child_id?`                           | monthly behavioural flags (lateness, repeated_attempt, weekend_cramming) |
| `recompute_patterns`   | `child_id?`                           | rebuild pattern_state                |
| `get_homework_load`    | `child_id?, weeks=8, extra_minutes_per_item?` | weekly bucket estimates              |

### Worth-a-chat (PTM list) — see also `get_ptm_brief`

| Tool                | Args                                  | Returns                              |
| ------------------- | ------------------------------------- | ------------------------------------ |
| `get_worth_a_chat`  | `child_id?, kind?, limit=200`         | every flagged item                    |
| `set_worth_a_chat`  | `item_id, flag (bool), note?`         | toggles the flag and audits the change |

`kind` accepts any item kind (`assignment` / `grade` / `comment` / `school_message`). The flag carries an optional note that gets surfaced verbatim in the PTM brief. Setting a note alone implicitly turns the flag on.

### Assignment state changes

| Tool                       | Args                          | Returns                              |
| -------------------------- | ----------------------------- | ------------------------------------ |
| `update_assignment`        | `item_id, parent_status?, priority?, snooze_until?, status_notes?, tags?, note?` | updated state |
| `mark_assignment_submitted`| `item_id`                     | parent-side submitted flag           |
| `unmark_assignment_submitted` | `item_id`                  | clear the parent-side submitted override |
| `set_self_prediction`      | `item_id, prediction (high/mid/low/%NN)` | Zimmerman pre-grade prediction       |
| `get_self_prediction_calibration` | `child_id?`            | summary + per-row history             |
| `summarize_assignment`     | `item_id, force=false`        | 1-sentence "the ask" (cached)        |
| `get_assignment_history`   | `item_id, limit=200`          | audit log per assignment              |

### School messages

| Tool                              | Args                  | Returns                              |
| --------------------------------- | --------------------- | ------------------------------------ |
| `get_messages`                    | `since_days=7, unread_only=false` | raw rows                  |
| `get_school_messages_grouped`     | `limit=50`            | dedup'd groups across kids            |
| `summarize_school_message_group`  | `group_id`            | 1-sentence Claude summary (cached)    |

### Events (camps, auditions, exams, holidays)

| Tool                            | Args                                                                      | Returns                              |
| ------------------------------- | ------------------------------------------------------------------------- | ------------------------------------ |
| `list_events`                   | `child_id?, days_ahead?, include_past=true`                                | calendar entries                     |
| `upsert_event`                  | `title, start_date, end_date?, start_time?, child_id?, event_type?, importance=1, location?, description?, notes?, source="manual", source_ref?, event_id?` | created/updated event |
| `delete_event`                  | `event_id`                                                                | `{ok, id}`                           |
| `extract_events_from_messages`  | `days=60, only_new=true`                                                  | LLM-driven extraction over school messages |

### Library (parent-uploaded files)

| Tool                       | Args                                                   | Returns                                |
| -------------------------- | ------------------------------------------------------ | -------------------------------------- |
| `list_library`             | `child_id?, kind?, subject?`                            | rows + LLM classification              |
| `reclassify_library_file`  | `library_id`                                            | re-runs the LLM classifier in place    |
| `delete_library_file`      | `library_id`                                            | `{ok, id}`                             |

### Portfolio (per-topic uploads)

| Tool                    | Args                                  | Returns                                |
| ----------------------- | ------------------------------------- | -------------------------------------- |
| `list_portfolio`        | `child_id, subject?, topic?`           | per-topic attachments                  |
| `delete_portfolio_file` | `attachment_id`                        | `{ok, id}` (only `portfolio_upload` rows) |

### Mindspark (Ei Mindspark progress)

| Tool                       | Args                  | Returns                              |
| -------------------------- | --------------------- | ------------------------------------ |
| `get_mindspark_progress`   | `child_id?`           | sessions[] + topics[] per kid        |
| `trigger_mindspark_sync`   | `child_id?`           | runs the slow scrape NOW (bypasses cadence guard) |
| `run_mindspark_recon`      | `child_id`            | recon-mode dump (HTML + XHR) for parser dev — slow ~3-5 min |

Mindspark scope is intentionally narrow: per-session aggregates + per-topic mastery only. **No question content, no answers, no responses** (see migration 0020 scope contract).

### File downloads — read content

These return file content directly (text or base64) capped at **5 MB**. For larger files, use the `resolve_*_path` tools on a local client and read off-disk. All downloads are path-traversal guarded.

| Tool                  | Args                                      | Returns                                                         |
| --------------------- | ----------------------------------------- | --------------------------------------------------------------- |
| `read_attachment`     | `attachment_id`                           | downloaded portal attachment                                     |
| `read_library_file`   | `library_id`                              | parent-uploaded library file                                     |
| `read_portfolio_file` | `attachment_id` (must be `portfolio_upload`) | per-topic portfolio attachment                                |
| `read_resource_file`  | `scope, category, filename, child_id?`    | portal-harvested resource file (`scope` = `schoolwide` or `kid`) |
| `read_spellbee_file`  | `child_id, filename`                      | Spelling Bee word-list file                                      |

### File uploads — push content

Counterparts to the read tools. Same 5 MB cap; same `{content, encoding}` shape so an upload→read round-trip is symmetric. `encoding="base64"` for any binary file (the default) or `encoding="text"` for plain UTF-8 text. SHA-256 dedup on the server keeps the same content from accumulating multiple rows.

| Tool                    | Args                                                                 | Notes                                                                  |
| ----------------------- | -------------------------------------------------------------------- | ---------------------------------------------------------------------- |
| `upload_library_file`   | `filename, content, encoding="base64", child_id?, note?`              | textbook PDFs / EPUBs / study material; LLM classification kicks off async |
| `upload_portfolio_file` | `child_id, subject, topic, filename, content, encoding="base64", note?` | per-(subject, topic) attachment for a kid                              |
| `upload_spellbee_file`  | `child_id, filename, content, encoding="base64"`                      | list-number auto-detected from filename                                |

Response shape:

```json
{
  "filename": "spellbee_list07.pdf",
  "mime_type": "application/pdf",
  "size_bytes": 18452,
  "encoding": "base64",         // "text" for text/* + JSON/XML/YAML
  "content": "<…base64 or UTF-8 text…>",
  "truncated": false,
  "max_bytes": 5242880
}
```

### File listings + path resolution (for local clients)

| Tool                       | Args                                                | Returns                                |
| -------------------------- | --------------------------------------------------- | -------------------------------------- |
| `list_attachments`         | `child_id?, source_kind?, limit=200`                | every downloaded attachment             |
| `list_resources`           | `child_id?, category?, scope?`                      | portal-harvested directory tree         |
| `list_spellbee_lists`      | `child_id?`                                         | Spelling Bee uploads per kid            |
| `resolve_attachment_path`  | `attachment_id`                                     | absolute filesystem path                |
| `resolve_resource_path`    | `scope, category, filename, child_id?`              | absolute filesystem path                |
| `resolve_spellbee_path`    | `child_id, filename`                                | absolute filesystem path                |
| `get_spellbee_linked_assignments` | `child_id?`                                  | every Spell Bee assignment + matched list |
| `delete_spellbee_list`     | `child_id, filename`                                | `{ok}`                                  |
| `rename_spellbee_list`     | `child_id, filename, new_name`                      | renamed entry                           |

### Notifications

| Tool                            | Args                                                | Returns                                |
| ------------------------------- | --------------------------------------------------- | -------------------------------------- |
| `get_notifications`             | `since_days=7, kinds?, child_id?, limit=100`         | events + per-channel status            |
| `replay_notifications`          | `since_days=7, child_id?`                           | dry-run replay against current rules   |
| `list_notification_snoozes`     | —                                                   | active parent snoozes                  |
| `add_notification_snooze`       | `rule_id, until (ISO), child_id?, reason?`           | upserted snooze                        |
| `delete_notification_snooze`    | `snooze_id`                                          | `{ok, id}`                             |

### Channels & digests

| Tool                       | Args                                                | Returns                                |
| -------------------------- | --------------------------------------------------- | -------------------------------------- |
| `get_channel_config`       | —                                                   | telegram/slack/email config            |
| `update_channel_config`    | `payload`                                           | merged config                          |
| `test_channel`             | `channel`                                           | sends a test message                   |
| `get_digest`               | `date_iso?`                                         | pre-rendered digest                    |
| `get_digest_preview`       | —                                                   | tonight's digest dry-run               |
| `send_digest`              | —                                                   | dispatch the digest now                |

### Sync observability

| Tool                          | Args                                            | Returns                                |
| ----------------------------- | ----------------------------------------------- | -------------------------------------- |
| `get_sync_runs`               | `tier?, since_days?, status?, limit=20`          | recent sync_runs rows                  |
| `get_sync_run_log`            | `run_id`                                         | full log_text                          |
| `get_concurrency_check`       | —                                                | which sync ids hold the on-disk lock   |
| `get_veracross_status`        | —                                                | freshness / last sync                  |
| `trigger_sync`                | `tier="light", blocking=false`                  | runs sync (light/medium/heavy)         |
| `prune_sync_runs`             | `days=7`                                         | drop sync_runs older than N days (admin) |

### Misc

| Tool                  | Args                                            | Returns                                |
| --------------------- | ----------------------------------------------- | -------------------------------------- |
| `ask`                 | `query, child_id?, kinds?, since_days?, limit=10` | FTS5 passages across all unstructured content |
| `add_note`            | `text, child_id?, tags?`                         | `{id, created_at}`                     |
| `get_notes`           | `child_id?`                                      | parent notes                           |
| `get_comments`        | `child_id?`                                      | teacher comments                       |
| `get_summaries`       | `kind?, limit=60`                                | weekly/monthly summaries               |
| `get_mcp_activity`    | `since_days=7, limit=200`                        | MCP audit log                          |

## The `ask` tool — free-form Q&A

Backed by SQLite **FTS5** (Porter stemming, unicode). Indexed kinds: `assignment`, `comment`, `message`, `school_message`, `article`, `note`. Each row returns `kind`, `subject`, `title`, a BM25-ranked snippet, `external_id`, `created_at`, and `score`. The caller's LLM composes the answer from the passages.

```text
User:   "What was that cricket camp fee thing?"
Claude: → ask(query="cricket camp fee")
        → sees a school_message about Classes 3-5 camp starting 22 Apr
        → composes: "Vasant Valley announced a cricket camp for Classes 3-5
                     starting Mon 22 Apr; fee portal registration required.
                     If interested for Samarth (4C), go to the fee portal."
```

## File downloads vs path resolution

There are **two** ways to get a file's content via MCP:

1. **`read_*` tools** — return the bytes directly inline. Good for HTTP-mounted clients that can't see the local disk, and for content Claude needs to read into context. Capped at 5 MB; binary returns base64.
2. **`resolve_*_path` tools** — return absolute filesystem paths. Good for local stdio clients (Claude Desktop, Claude Code) that have disk access — let the client's `Read` tool slurp the file off disk without round-tripping through MCP.

Pick `read_*` for HTTP transports or anything bigger than what fits comfortably in a tool result. Pick `resolve_*_path` for local stdio clients on files that don't need to be in the model's context window.

## Audit trail

Every tool call writes to `mcp_tool_calls`:

```text
id | tool | client_id | arguments_json | result_preview | row_count | duration_ms | created_at | error
```

Surfaced in the web UI under `/notifications → MCP activity` tab. Useful for spotting runaway clients or debugging what Dispatch / OpenClaw are actually asking for. Auditing happens in a `try…finally` so a failing audit never breaks a tool call.

## Client configurations

There are two ways to connect every client: **stdio** (the local `schoolwork-mcp` process talks directly to the SQLite DB) or **HTTP** (the running `schoolwork-api` serves MCP at `/mcp`). Stdio is fastest and needs no bearer token. HTTP is the only option when the consumer can't run a local Python process — Claude Dispatch, OpenClaw, anything in the cloud.

### Claude Desktop

**Config file location:**
- macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`
- Windows: `%APPDATA%\Claude\claude_desktop_config.json`
- Linux: `~/.config/Claude/claude_desktop_config.json`

**A. Stdio (recommended — local, no auth, fastest):**

```json
{
  "mcpServers": {
    "parent-cockpit": {
      "command": "uv",
      "args": [
        "--directory", "/Users/varun/dev/schoolwork",
        "run", "schoolwork-mcp"
      ]
    }
  }
}
```

**B. HTTP (when Desktop runs on a different machine than `schoolwork-api`):**

Recent Claude Desktop builds support HTTP MCP natively:

```json
{
  "mcpServers": {
    "parent-cockpit": {
      "transport": "http",
      "url": "https://your-host/mcp",
      "headers": {
        "Authorization": "Bearer YOUR_TOKEN"
      }
    }
  }
}
```

If your Claude Desktop build doesn't recognise `transport: "http"`, use `mcp-remote` as a stdio↔HTTP bridge:

```json
{
  "mcpServers": {
    "parent-cockpit": {
      "command": "npx",
      "args": [
        "-y", "mcp-remote",
        "https://your-host/mcp",
        "--header", "Authorization:Bearer YOUR_TOKEN"
      ]
    }
  }
}
```

`mcp-remote` ships on npm (`npm install -g mcp-remote` or use `npx -y` as above).

**Restart Claude Desktop** after editing the config. Tools appear under the 🔌 menu.

### Claude Code

**Stdio (per-project, recommended):**

`.claude/settings.local.json` in the repo:

```json
{
  "mcpServers": {
    "parent-cockpit": {
      "command": "uv",
      "args": ["run", "schoolwork-mcp"]
    }
  }
}
```

Or globally (`~/.claude/settings.json`):

```json
{
  "mcpServers": {
    "parent-cockpit": {
      "command": "uv",
      "args": [
        "--directory", "/Users/varun/dev/schoolwork",
        "run", "schoolwork-mcp"
      ]
    }
  }
}
```

**HTTP** (when Claude Code runs in a different repo or container):

Same `transport: "http"` + headers shape as Claude Desktop, or use the `mcp-remote` bridge.

You can also wire it via the CLI:

```bash
claude mcp add parent-cockpit \
  --transport http \
  --url https://your-host/mcp \
  --header "Authorization: Bearer YOUR_TOKEN"
```

### Claude Agent SDK / Claude API direct

If you're driving Claude programmatically with the Agent SDK and want it to call the cockpit's tools, register the MCP server in your agent config:

```python
# agent_config.py — Python SDK example
mcp_servers = {
    "parent-cockpit": {
        "transport": "http",
        "url": "https://your-host/mcp",
        "headers": {"Authorization": f"Bearer {os.environ['MCP_BEARER_TOKEN']}"},
    }
}
```

Stdio works too if your agent is on the same host as the cockpit:

```python
mcp_servers = {
    "parent-cockpit": {
        "command": "uv",
        "args": ["--directory", "/Users/varun/dev/schoolwork", "run", "schoolwork-mcp"],
    }
}
```

### Claude Dispatch (HTTP, scheduled agent)

In Dispatch's MCP server config:

| Field | Value |
| --- | --- |
| Transport | Streamable HTTP |
| URL | `https://your-host/mcp` |
| Auth header | `Authorization: Bearer YOUR_TOKEN` |

Dispatch can then compose digests, run ad-hoc cockpit queries, and trigger `trigger_sync` / `trigger_mindspark_sync` on its own cadence.

### OpenClaw (HTTP or SSE)

Whichever transport OpenClaw prefers — both are served. Same bearer token. If OpenClaw supports multiple MCP servers, add this alongside others; the `instructions=` string at the top of `backend/app/mcp/server.py` tells OpenClaw's LLM how to navigate the surface.

In OpenClaw's MCP server settings:

| Field | Streamable HTTP | SSE |
| --- | --- | --- |
| URL | `https://your-host/mcp` | `https://your-host/mcp-sse` |
| Auth | `Bearer YOUR_TOKEN` (same token works for both transports) |

If OpenClaw uses a config-file format, the shape is usually:

```yaml
mcp_servers:
  - name: parent-cockpit
    transport: streamable_http
    url: https://your-host/mcp
    headers:
      Authorization: Bearer YOUR_TOKEN
```

### Exposing your cockpit off-LAN

If `schoolwork-api` only listens on `127.0.0.1`, the simplest hardened setup is:

1. **Tailscale** — install on the machine running `schoolwork-api` and on every client. Each client connects to the cockpit's MagicDNS hostname (`http://your-mac:7778/mcp`). Bearer token still required, but you've eliminated the public-internet attack surface.
2. **Cloudflare Tunnel** — `cloudflared tunnel --url http://localhost:7778`. Cloudflare proxies `https://<random>.trycloudflare.com` (or your subdomain) to your local port. Still set `MCP_BEARER_TOKEN`.
3. **Reverse proxy on a real host** — nginx/caddy in front of port 7778 with TLS termination. Add IP allowlists or mTLS at the proxy if you want defence in depth.

Whatever you pick, **set `MCP_BEARER_TOKEN`** before exposing the host. The 91-tool surface includes destructive operations (`update_assignment`, `delete_event`, `delete_library_file`, `trigger_mindspark_sync`, `read_attachment` for any kid's downloads) — you do not want this open.

## Local dev

```bash
# Run the API + HTTP MCP together (port from APP_PORT, default 7777):
uv run schoolwork-api

# Health (no auth, always open):
curl http://127.0.0.1:7777/health
# → {... "mcp_auth_required": false ...}   (or true once you set the token)

# Hit MCP without a token while MCP_BEARER_TOKEN is unset → works:
curl -X POST http://127.0.0.1:7777/mcp \
     -H 'Accept: application/json, text/event-stream' \
     -H 'Content-Type: application/json' \
     -d '{"jsonrpc":"2.0","method":"tools/list","id":1}'

# Same call after setting MCP_BEARER_TOKEN → 401 unless you include header:
curl -X POST http://127.0.0.1:7777/mcp \
     -H 'Accept: application/json, text/event-stream' \
     -H 'Content-Type: application/json' \
     -H "Authorization: Bearer $MCP_BEARER_TOKEN" \
     -d '{"jsonrpc":"2.0","method":"tools/list","id":1}'

# Stdio MCP alone (for Claude Desktop/Code):
uv run schoolwork-mcp

# Tool-list smoke test:
uv run python -c "
from app.mcp import server as S
import asyncio
tools = asyncio.run(S.server.list_tools())
print(f'{len(tools)} tools registered:')
for t in sorted(tools, key=lambda t: t.name):
    print(f'  {t.name}')
"
```

## Coverage

Every meaningful FastAPI endpoint has a matching MCP tool. The audit (every `@app.<verb>("/api/...")` cross-checked against `@server.tool()` definitions) leaves only these endpoints intentionally **not** exposed via MCP:

| Endpoint                              | Why it's not an MCP tool                                                  |
| ------------------------------------- | ------------------------------------------------------------------------- |
| `GET /` (HTML home)                   | UI surface, not data                                                      |
| `GET /health`                         | Liveness probe — meant for ops, not LLM consumption                       |
| `GET /api/ui-prefs` / `PUT /api/ui-prefs` | Device-local UI state (collapsed bucket order, etc.) — has no agent value |
| `GET /api/veracross/credentials` / `PUT /api/veracross/credentials` | Security-sensitive secrets — kept out of LLM context window               |
| `GET /api/veracross/login/*` / `POST /api/veracross/login/*` / `DELETE /api/veracross/login` | Interactive captcha-fallback login flow with screenshots — designed for the React UI, makes no sense in MCP |

If you need any of these for a specific automation, ping the file owner — most can be added but were left out by design.

## Adding a new tool

1. Add the function in `backend/app/mcp/server.py` decorated with `@server.tool()`. Keep the signature small and explicit (no kwargs blobs).
2. Wrap the body in the standard `started/err/result` pattern with the `_audit(...)` call in `finally` — that way every call lands in `mcp_tool_calls` regardless of outcome.
3. Add an entry to the table in this file under the right domain section.
4. Update the `instructions=` string in `FastMCP(...)` so prompt-only callers know the tool exists.
5. Smoke-test:
   ```bash
   uv run python -c "from app.mcp import server; import asyncio; print(len(asyncio.run(server.server.list_tools())))"
   ```
