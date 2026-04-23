# Addendum to BUILDSPEC v2 — MCP layer + "ask anything"

**Relationship to BUILDSPEC.md:** additive. BUILDSPEC remains the plan of record for the web app, scraper, notability engine, and digest. This addendum adds an MCP layer that sits alongside the FastAPI app, reading the same SQLite DB, so Claude clients (Dispatch, OpenClaw, Claude Desktop, ad-hoc MCP callers) can query and act on the same data — including free-form "ask a question" routed through the caller's LLM.

**Why this is not deferred past v2:** the user relies on Dispatch/OpenClaw/Cowork as daily surfaces. Shipping the web-only product without these would mean maintaining two separate query paths later. The MCP server is ~300 LOC once the DB + models exist; adding it in W1-W2 is cheaper than bolting it on later.

---

## A. Architectural placement

```
                  ┌────────────────────────────────┐
                  │  Clients                       │
                  │  ─ Web UI (React)              │
                  │  ─ Telegram / SMTP (dispatched)│
                  │  ─ Claude Dispatch / OpenClaw  │──┐
                  │  ─ Claude Desktop              │  │ MCP (stdio or HTTP/SSE)
                  │  ─ Any MCP client              │──┘
                  └──────┬───────────────────┬─────┘
                         │                   │
                         │ HTTP              │
                  ┌──────▼──────────┐ ┌──────▼─────────────┐
                  │ FastAPI app     │ │ MCP server         │
                  │ (web + jobs +   │ │ FastMCP, both      │
                  │  notability)    │ │ stdio + HTTP/SSE   │
                  └──────┬──────────┘ └──────┬─────────────┘
                         │                   │
                         └────────┬──────────┘
                                  │
                         ┌────────▼────────┐
                         │  SQLite app.db  │
                         │  (WAL, shared)  │
                         └────────┬────────┘
                                  │
                           ┌──────▼──────┐
                           │  FTS5 index │   (for `ask`)
                           └─────────────┘
```

- **One SQLite file, two processes** (or one — see below). FastAPI owns the scheduler and write path; MCP is read-mostly.
- **Co-location option:** both run inside the same Uvicorn process, FastAPI mounted at `/` and the MCP SSE endpoint mounted at `/mcp`. Saves a container. Pick this unless operational pressure forces split.
- **Transport duality:** stdio mode launched per-client by Claude Desktop/Code via `uv run schoolwork-mcp`. HTTP/SSE served by the same FastAPI app for Dispatch/OpenClaw/remote callers.

## B. MCP tool surface (v1)

| Tool | Purpose | Arguments | Returns |
|---|---|---|---|
| `list_children` | Enumerate kids + classes + IDs | — | `[{id, name, class}]` |
| `get_today` | Current Today-view state (same shape as the 4pm digest) | `child_id?` | `DigestData` JSON |
| `get_overdue` | Overdue assignments | `child_id?`, `since?` | `[Assignment]` |
| `get_due_today` | Due today | `child_id?` | `[Assignment]` |
| `get_upcoming` | Upcoming window | `child_id?`, `days=14` | `[Assignment]` |
| `get_grades` | Recent grades with trend | `child_id`, `subject?`, `window_days=30` | `[Grade] + trend` |
| `get_messages` | School messages | `since?`, `unread_only?` | `[Message]` |
| `get_notifications` | Events + delivery status | `since?`, `kinds?`, `child_id?` | `[Event]` |
| `get_digest` | Render a digest (today or any past date) | `date?`, `channel='web'` | rendered markdown/html |
| `trigger_sync` | Manually trigger a scraper sync | — | `sync_run_id`, status |
| `ask` | Free-form semantic/FTS search across all stored text | `query`, `child_id?`, `kinds?`, `since?`, `limit=10` | `[{passage, metadata, score, link}]` |
| `add_note` | Append a parent note (optionally about a child/item) | `text`, `child_id?`, `related_item_id?`, `tags?` | `note_id` |
| `get_notes` | Retrieve parent notes | `child_id?`, `since?`, `tags?` | `[Note]` |

**Design rule:** tools return raw structured JSON. Prose synthesis is the caller LLM's job. The only tool that can return synthesized prose is `get_digest` (because that prose is pre-computed and cached in `summaries`, per §8 of BUILDSPEC).

## C. `ask` — free-form Q&A over unstructured content

**Problem:** the user needs to ask things like "did any teacher comment mention Samarth's handwriting this month?" or "when's the Cricket Camp again?" and have the answer surface from wherever it lives — a teacher comment, a school message body, an assignment description, an article.

**Approach (v1 — ship this in W2):** SQLite FTS5 virtual table indexing every text-bearing row. Return top-K matching passages to the caller; let the caller's LLM synthesize.

```sql
CREATE VIRTUAL TABLE search_index USING fts5(
    kind,              -- 'assignment' | 'comment' | 'message' | 'article' | 'note'
    child_id UNINDEXED,
    subject,
    title,
    body,
    external_id UNINDEXED,
    created_at UNINDEXED,
    tokenize = "porter unicode61"
);
```

Maintained via AFTER INSERT/UPDATE/DELETE triggers on `veracross_items` (for kind in subset) and `parent_notes`.

**Approach (v2 — add later if needed):** hybrid retrieval with `sqlite-vec` for embeddings, combined with FTS via Reciprocal Rank Fusion. Only if FTS recall turns out to be insufficient for the queries the user asks most.

**`ask` tool response shape:**

```json
{
  "query": "cricket camp",
  "results": [
    {
      "kind": "message",
      "child_id": null,
      "subject": null,
      "title": "Cricket Camp — Classes 3 to 5",
      "snippet": "… new cricket camp started Mon 22 Apr (earlier week). Fee portal …",
      "score": 0.92,
      "external_id": "msg-4428",
      "created_at": "2026-04-16T10:00:00+05:30",
      "link": "https://portals.veracross.eu/vasantvalleyschool/parent/messages/..."
    }
  ]
}
```

Caller's LLM composes the answer from `results`.

## D. Auditing every MCP call

New table `mcp_tool_calls`:

```sql
CREATE TABLE mcp_tool_calls (
    id              INTEGER PRIMARY KEY,
    tool            TEXT NOT NULL,
    arguments_json  TEXT NOT NULL,
    client_id       TEXT,              -- 'dispatch' | 'openclaw' | 'claude-desktop' | custom
    result_preview  TEXT,               -- first 300 chars / count of rows returned
    row_count       INTEGER,
    error           TEXT,
    duration_ms     INTEGER,
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX idx_mcp_tool_calls_tool_time ON mcp_tool_calls(tool, created_at DESC);
```

- Every tool invocation logs a row.
- `client_id` sniffed from MCP `clientInfo.name` during handshake.
- `/notifications` view gets a second tab "MCP activity" showing recent tool calls — makes it visible what Dispatch and OpenClaw are doing.

## E. Channel config extension

Add `channel: 'mcp'` to the `channels` config object in settings for policy-gated tools (write-path only — `trigger_sync`, `add_note`). Read tools are ungated.

```yaml
channels:
  ...
  mcp:
    enabled: true
    allowed_clients: ["dispatch", "openclaw", "claude-desktop"]
    allowed_write_tools: ["add_note", "trigger_sync"]
```

## F. Deployment

- **Local dev:** `uv run schoolwork-mcp --stdio` for Claude Desktop/Code; `uv run uvicorn backend.app.main:app` exposes `/mcp/sse` for HTTP/SSE clients.
- **Dispatch:** add the HTTP/SSE endpoint URL + a bearer token to the Dispatch MCP config. All tools callable from scheduled agents.
- **OpenClaw:** whatever transport it prefers, the server supports both without code changes.
- **Auth for HTTP/SSE:** simple bearer token from `.env` — `MCP_BEARER_TOKEN=...`. Validated in a FastAPI dependency. Stdio needs no auth (local only).

## G. Where in the build sequence

| Weekend | What ships |
|---|---|
| **W1** (scraper-first vertical slice) | Add to the existing W1 scope: MCP server skeleton + `list_children` + `get_overdue` + `get_digest` (when digest exists, else 404). Stdio transport only. Smoke test from Claude Code. |
| **W2** (notability + notifications) | MCP gets `get_notifications`, `trigger_sync`, `add_note`/`get_notes`. HTTP/SSE endpoint at `/mcp/sse` with bearer auth. Dispatch integration configured. `mcp_tool_calls` audit table + migration. |
| **W2–W3** | `ask` tool + FTS5 virtual table + triggers. Ships with W3 because syllabus content should be indexed too. |
| **W3** | All digest-related tools (`get_today`, `get_messages`, `get_upcoming`, grade trends) return complete payloads. |
| **W4** | `/mcp/sse` activity visible in the UI's notifications pane (second tab). Polish + docs. |

This keeps the weekend deliverables intact and adds MCP as a parallel track per weekend, not a fifth weekend.
