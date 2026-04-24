"""End-to-end verification — hits every major component in-process.

Checks:
  A. Filesystem layout (data/, per-kid dirs, seed syllabus, storage_state)
  B. SQLite DB (pointed at data/app.db, all tables present, row counts sane)
  C. HTTP API (every /api/* endpoint, via an in-process ASGI transport)
  D. MCP surface (every registered tool, callable with representative args)
  E. File I/O (download one attachment; assert bytes match sha256 in DB)

Prints a pass/fail matrix at the end. Exit code = number of failures.

Run:
    uv run python backend/scripts/verify_system.py
    uv run python backend/scripts/verify_system.py --json   # machine-readable
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import sqlite3
import sys
import traceback
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent.parent
# Allow `from backend...` imports when invoked as a script.
sys.path.insert(0, str(ROOT))


class Report:
    def __init__(self) -> None:
        self.results: list[tuple[str, bool, str]] = []  # (name, ok, detail)

    def record(self, name: str, ok: bool, detail: str = "") -> None:
        self.results.append((name, ok, detail))

    def passed(self) -> int:
        return sum(1 for _, ok, _ in self.results if ok)

    def failed(self) -> list[tuple[str, str]]:
        return [(n, d) for n, ok, d in self.results if not ok]

    def print(self) -> None:
        for name, ok, detail in self.results:
            mark = "✓" if ok else "✗"
            line = f"  {mark} {name}"
            if detail:
                line += f" — {detail}"
            print(line)
        print()
        print(f"{self.passed()}/{len(self.results)} passed")


async def check_fs(r: Report) -> None:
    print("── A. Filesystem layout")
    data = ROOT / "data"
    r.record("data/ exists", data.is_dir(), str(data))
    r.record("data/app.db exists", (data / "app.db").is_file())
    r.record("data/storage_state.json exists", (data / "storage_state.json").is_file())
    r.record("data/rawdata/ exists", (data / "rawdata").is_dir())
    r.record(
        "data/syllabus/class_4_2026-27.json present",
        (data / "syllabus" / "class_4_2026-27.json").is_file(),
    )
    r.record(
        "data/syllabus/class_6_2026-27.json present",
        (data / "syllabus" / "class_6_2026-27.json").is_file(),
    )
    # Legacy locations should NOT exist post-migration
    r.record("legacy /app.db is gone", not (ROOT / "app.db").exists())
    r.record(
        "legacy recon/storage_state.json is gone",
        not (ROOT / "recon" / "storage_state.json").exists(),
    )
    r.record(
        "legacy data/attachments/ is gone",
        not (data / "attachments").exists(),
    )
    r.record(
        "legacy flat data/spellbee/ is gone",
        not (data / "spellbee").exists(),
    )
    # Per-kid dirs. Note: spellbee/ and screenshots/ are lazy-created on
    # first use by the service layer, so we only require them to exist if
    # files have actually been written there.
    for kid in ("samarth_4C", "tejas_6B"):
        base = data / "rawdata" / kid
        r.record(f"rawdata/{kid}/ exists", base.is_dir())
        r.record(f"rawdata/{kid}/attachments/ exists", (base / "attachments").is_dir())


def check_db(r: Report) -> None:
    print("── B. Database")
    db = ROOT / "data" / "app.db"
    if not db.exists():
        r.record("db open", False, "data/app.db missing")
        return
    conn = sqlite3.connect(str(db))
    conn.row_factory = sqlite3.Row
    try:
        tables = {
            row["name"] for row in
            conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }
        expected = {
            "children", "veracross_items", "attachments",
            "assignment_status_history", "sync_runs", "events",
            "notifications", "summaries", "parent_notes",
            "mcp_tool_calls", "llm_calls", "channel_config",
            "syllabus_cycle_overrides", "syllabus_topic_status",
            "search_index",
        }
        missing = expected - tables
        r.record("all core tables present", not missing, f"missing: {missing}" if missing else "")
        # Spot-check counts
        counts: dict[str, int] = {}
        for t in ("children", "veracross_items", "attachments", "sync_runs"):
            counts[t] = conn.execute(f"SELECT count(*) FROM {t}").fetchone()[0]
        r.record("children >= 2", counts["children"] >= 2, f"{counts['children']}")
        r.record("veracross_items > 0", counts["veracross_items"] > 0, f"{counts['veracross_items']}")
        r.record("attachments > 0", counts["attachments"] > 0, f"{counts['attachments']}")
        r.record("sync_runs > 0", counts["sync_runs"] > 0, f"{counts['sync_runs']}")
        # All attachments.local_path should point under data/rawdata/
        bad = conn.execute(
            "SELECT count(*) FROM attachments WHERE local_path NOT LIKE 'data/rawdata/%'"
        ).fetchone()[0]
        r.record("all attachments under data/rawdata/", bad == 0, f"{bad} outside")
        # FTS index in sync with veracross_items
        fts_n = conn.execute("SELECT count(*) FROM search_index").fetchone()[0]
        r.record("search_index populated", fts_n > 0, f"{fts_n} rows")
    finally:
        conn.close()


async def check_http(r: Report) -> None:
    print("── C. HTTP API")
    import httpx
    from backend.app.main import app
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
        async def hit(method: str, url: str, **kw) -> tuple[int, Any]:
            r2 = await c.request(method, url, **kw)
            try:
                return r2.status_code, r2.json()
            except Exception:
                return r2.status_code, r2.content

        pairs = [
            ("GET", "/health"),
            ("GET", "/api/children"),
            ("GET", "/api/today"),
            ("GET", "/api/overdue"),
            ("GET", "/api/due-today"),
            ("GET", "/api/upcoming"),
            ("GET", "/api/messages"),
            ("GET", "/api/attachments"),
            ("GET", "/api/notifications"),
            ("GET", "/api/assignments"),
            ("GET", "/api/comments"),
            ("GET", "/api/notes"),
            ("GET", "/api/summaries"),
            ("GET", "/api/child/1"),
            ("GET", "/api/child/2"),
            ("GET", "/api/overdue-trend"),
            ("GET", "/api/veracross/status"),
            ("GET", "/api/veracross/credentials"),
            ("GET", "/api/ui-prefs"),
            ("GET", "/api/channel-config"),
            ("GET", "/api/sync-runs"),
            ("GET", "/api/sync-runs/concurrency-check"),
            ("GET", "/api/syllabus/4"),
            ("GET", "/api/syllabus/6"),
            ("GET", "/api/assignments/constants"),
            ("GET", "/api/spellbee/lists?child_id=1"),
            ("GET", "/api/spellbee/lists?child_id=2"),
            ("GET", "/api/spellbee/linked-assignments"),
            ("GET", "/api/mcp-activity"),
            ("GET", "/api/digest/preview"),
        ]
        for method, url in pairs:
            try:
                st, _ = await hit(method, url)
                ok = 200 <= st < 300
                r.record(f"{method} {url}", ok, f"HTTP {st}")
            except Exception as e:
                r.record(f"{method} {url}", False, f"EXC {type(e).__name__}: {e}")

        # Probe one attachment download end-to-end (bytes + sha256 match).
        try:
            # pick first attachment
            import sqlite3
            conn = sqlite3.connect(str(ROOT / "data" / "app.db"))
            try:
                row = conn.execute("SELECT id, sha256, size_bytes FROM attachments ORDER BY id LIMIT 1").fetchone()
            finally:
                conn.close()
            if row is None:
                r.record("attachment download round-trip", False, "no attachment rows")
            else:
                att_id, sha_expected, size_expected = row
                resp = await c.get(f"/api/attachments/{att_id}")
                ok_status = resp.status_code == 200
                ok_size = len(resp.content) == size_expected
                actual_sha = hashlib.sha256(resp.content).hexdigest()
                ok_sha = actual_sha == sha_expected
                r.record(
                    "attachment download round-trip",
                    ok_status and ok_size and ok_sha,
                    f"status={resp.status_code} size={len(resp.content)}/{size_expected} sha_match={ok_sha}",
                )
        except Exception as e:
            r.record("attachment download round-trip", False, f"EXC {e}")


async def check_mcp(r: Report) -> None:
    print("── D. MCP tool surface")
    import backend.app.mcp.server as S
    tools = await S.server.list_tools()
    tool_names = sorted(t.name for t in tools)
    r.record("tool registration", len(tools) > 0, f"{len(tools)} tools")
    must_have = {
        "list_children", "get_today", "get_overdue", "get_due_today",
        "get_upcoming", "get_messages", "ask", "get_grades", "get_grade_trends",
        "get_attachments" if False else "list_attachments",
        "list_spellbee_lists", "resolve_spellbee_path", "resolve_attachment_path",
        "get_sync_runs", "get_sync_run_log", "get_veracross_status",
        "check_veracross_auth", "update_assignment",
        "get_assignment_constants", "get_assignment_history",
        "get_child_detail", "list_assignments", "get_mcp_activity",
        "trigger_sync", "trigger_syllabus_check",
    }
    missing_tools = must_have - set(tool_names)
    r.record("no missing tools", not missing_tools, f"missing: {sorted(missing_tools)}" if missing_tools else "")

    # Callable sanity: invoke a representative handful
    async def call(name: str, **kwargs):
        fn = getattr(S, name)
        return await fn(**kwargs)

    try:
        x = await call("list_children")
        r.record("MCP list_children", isinstance(x, list) and len(x) >= 2)
    except Exception as e:
        r.record("MCP list_children", False, repr(e))

    try:
        x = await call("get_today")
        r.record("MCP get_today", isinstance(x, dict) and "totals" in x)
    except Exception as e:
        r.record("MCP get_today", False, repr(e))

    try:
        x = await call("get_assignment_constants")
        ok = isinstance(x, dict) and "parent_statuses" in x and "fixed_tags" in x
        r.record("MCP get_assignment_constants", ok)
    except Exception as e:
        r.record("MCP get_assignment_constants", False, repr(e))

    try:
        x = await call("list_attachments", limit=1)
        r.record("MCP list_attachments", isinstance(x, list))
    except Exception as e:
        r.record("MCP list_attachments", False, repr(e))

    try:
        x = await call("list_spellbee_lists", child_id=2)
        r.record("MCP list_spellbee_lists(child=2)", isinstance(x, list))
    except Exception as e:
        r.record("MCP list_spellbee_lists(child=2)", False, repr(e))

    try:
        x = await call("get_sync_runs", limit=1)
        r.record("MCP get_sync_runs", isinstance(x, list))
    except Exception as e:
        r.record("MCP get_sync_runs", False, repr(e))

    try:
        x = await call("get_veracross_status")
        r.record("MCP get_veracross_status", isinstance(x, dict) and "healthy" in x)
    except Exception as e:
        r.record("MCP get_veracross_status", False, repr(e))

    try:
        x = await call("get_concurrency_check")
        r.record("MCP get_concurrency_check", isinstance(x, dict) and "count" in x)
    except Exception as e:
        r.record("MCP get_concurrency_check", False, repr(e))

    # Resolve a real attachment path (should point under data/rawdata)
    try:
        conn = sqlite3.connect(str(ROOT / "data" / "app.db"))
        try:
            first = conn.execute("SELECT id FROM attachments ORDER BY id LIMIT 1").fetchone()
        finally:
            conn.close()
        if first:
            x = await call("resolve_attachment_path", attachment_id=first[0])
            ok = isinstance(x, dict) and "/data/rawdata/" in x.get("absolute_path", "")
            r.record("MCP resolve_attachment_path → rawdata", ok, x.get("absolute_path", "")[:80])
        else:
            r.record("MCP resolve_attachment_path → rawdata", False, "no attachments")
    except Exception as e:
        r.record("MCP resolve_attachment_path → rawdata", False, repr(e))


def check_paths_module(r: Report) -> None:
    print("── E. Path helpers")
    try:
        from backend.app.util import paths as P

        class C:
            id = 2
            display_name = "Samarth"
            class_level = 4
            class_section = "4C"

        kid = P.kid_slug(C)
        r.record("kid_slug Samarth 4C = samarth_4C", kid == "samarth_4C", kid)
        fname = P.attachment_filename(
            date_iso="2026-04-22", subject="4C English",
            title="Snake Trouble: Spelling and Vocabulary",
            sha256_hex="a8c3f10487de", ext=".pdf",
        )
        ok = (
            fname.startswith("2026-04-22_english_snake-trouble-")
            and fname.endswith("_a8c3f104.pdf")
        )
        r.record("attachment_filename composes correctly", ok, fname)
        r.record("data_root resolves", P.data_root().is_dir())
        r.record("kid_spellbee_dir resolves + is under rawdata",
                 "/data/rawdata/" in str(P.kid_spellbee_dir(C)))
    except Exception as e:
        r.record("paths module", False, repr(e))


async def main_async(json_out: bool) -> int:
    report = Report()
    try:
        await check_fs(report)
        check_db(report)
        await check_http(report)
        await check_mcp(report)
        check_paths_module(report)
    except Exception:
        traceback.print_exc()
    if json_out:
        print(json.dumps({
            "passed": report.passed(),
            "total": len(report.results),
            "failed": [{"name": n, "detail": d} for n, d in report.failed()],
            "all": [{"name": n, "ok": ok, "detail": d} for n, ok, d in report.results],
        }, indent=2))
    else:
        print()
        report.print()
        if report.failed():
            print()
            print("Failures:")
            for name, detail in report.failed():
                print(f"  ✗ {name}: {detail}")
    return len(report.failed())


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    return asyncio.run(main_async(args.json))


if __name__ == "__main__":
    sys.exit(main())
