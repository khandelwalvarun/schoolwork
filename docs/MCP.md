# MCP server — Dispatch / OpenClaw / Claude Desktop wiring

> Adds to BUILDSPEC.md §3. See also `docs/BUILDSPEC_ADDENDUM_MCP.md` for rationale and the full tool surface.

## Transports

| Transport | Endpoint | Clients |
|---|---|---|
| **stdio** | `schoolwork-mcp` (installed as a console script) | Claude Desktop, Claude Code local |
| **Streamable HTTP** | `http://<host>/mcp` | Dispatch, OpenClaw, any modern MCP HTTP client |
| **SSE (legacy)** | `http://<host>/mcp-sse` | Older MCP clients that require SSE |

All three backends share the **same tool implementations** (in `backend/app/mcp/server.py`) and the **same SQLite DB**. Switching transports is a client-side decision — no server code changes.

## Auth

- **Stdio:** no auth (local process, trusted).
- **HTTP / SSE:** optional bearer token via env var `MCP_BEARER_TOKEN`. Leave blank in dev.
  - When set, clients must send `Authorization: Bearer <token>` on every request.

## Tools (v1)

| Tool | Kind | Arguments | Returns |
|---|---|---|---|
| `list_children` | read | — | `[{id, display_name, class_level, class_section, ...}]` |
| `get_today` | read | — | `{generated_at, totals, children[], messages_last_7d[], last_sync}` |
| `get_overdue` | read | `child_id?` | `[Assignment]` |
| `get_due_today` | read | `child_id?` | `[Assignment]` |
| `get_upcoming` | read | `child_id?`, `days=14` | `[Assignment]` |
| `get_messages` | read | `since_days=7`, `unread_only=false` | `[Message]` |
| `get_notifications` | read | `since_days=7`, `kinds?`, `child_id?`, `limit=100` | `[Event + per-channel status]` |
| `get_digest` | read | `date_iso?` | pre-rendered digest (or `null`) |
| `ask` | read | `query`, `child_id?`, `kinds?`, `since_days?`, `limit=10` | `{query, results[]}` — FTS5 passages |
| `add_note` | write | `text`, `child_id?`, `tags?` | `{id, created_at}` |
| `trigger_sync` | write | — | `{sync_run_id, status}` |

## The `ask` tool — free-form Q&A

Backed by SQLite **FTS5** (Porter stemming, unicode). Indexed kinds: `assignment`, `comment`, `message`, `school_message`, `article`, `note`. Each row returns `kind`, `subject`, `title`, a BM25-ranked snippet, `external_id`, `created_at`, and `score`. The caller's LLM composes the answer from the passages.

Example (from Claude/OpenClaw):

```
User:   "What was that cricket camp fee thing?"
Claude: → ask(query="cricket camp fee")
        → sees a school_message result about Classes 3–5 camp starting 22 Apr
        → composes: "Vasant Valley announced a cricket camp for Classes 3–5
                     starting Mon 22 Apr; fee portal registration required.
                     If interested for Samarth (4C), go to the fee portal."
```

## Client configurations

### Claude Desktop (stdio)

`~/.config/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "parent-cockpit": {
      "command": "uv",
      "args": ["--directory", "D:/claude/schoolwork", "run", "schoolwork-mcp"]
    }
  }
}
```

### Claude Code (stdio, per-project)

`.claude/settings.local.json` (or user-scope):

```json
{
  "mcpServers": {
    "parent-cockpit": { "command": "uv", "args": ["run", "schoolwork-mcp"] }
  }
}
```

### Claude Dispatch (HTTP)

Point the scheduled agent's MCP config at `https://<your-host>/mcp` with the bearer token. The agent can then compose digests, run ad-hoc queries, and call `trigger_sync` on its own cadence.

### OpenClaw (HTTP or SSE)

Whichever transport OpenClaw prefers — both are served. Same bearer token. If OpenClaw supports multiple MCP servers, add this alongside others; the `instructions` string in the server tells its LLM how to use the tools.

## Audit trail

Every tool call writes a row to `mcp_tool_calls`:

```
id | tool | client_id | arguments_json | result_preview | row_count | duration_ms | created_at
```

Surfaced in the web UI under `/notifications → MCP activity` tab. Useful for spotting runaway clients or debugging what Dispatch/OpenClaw are actually asking.

## Local dev

```bash
# Run the API + HTTP MCP together:
uv run schoolwork-api
# Then: curl http://127.0.0.1:7777/health
#       Dispatch/OpenClaw: http://127.0.0.1:7777/mcp

# Or run stdio MCP alone (for Claude Desktop/Code):
uv run schoolwork-mcp
```

## Roadmap

- **W2:** bearer-token enforcement middleware; per-tool rate limiting; `mcp_tool_calls` UI tab.
- **W3:** `get_grades`, grade-trend sparkline data, syllabus-context lookups exposed as tools.
- **W4:** hybrid FTS + embedding search if FTS recall turns out to be insufficient for the user's queries.
