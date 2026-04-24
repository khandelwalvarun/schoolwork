"""Portal resource harvester + frequency classifier.

Uses the authenticated scraper session to:
  1. Walk the parent-portal landing page's full tile sidebar.
  2. Expand each `/pages/<slug>` landing one hop to discover embedded docs.
  3. Download each downloadable tile (direct files + Google Drive).
  4. Classify every tile by:
       - category   (spellbee / reading / schedules / assessments / news /
                     general / syllabus / misc)
       - schoolwide (bool — lives in rawdata/schoolwide/ vs rawdata/<kid>/)
       - freq       (daily / weekly / monthly / termly / annual / onceoff)
       - sync_tier  (light / medium / heavy / manual) — what tier of the
                     sync schedule should re-pull this
  5. Save files under data/rawdata/<kid>/<category>/ (per-kid) or
     data/rawdata/schoolwide/<category>/ (everyone).

Writes a JSON report to data/resources_report.json.

Run:
  uv run python backend/scripts/harvest_resources.py           # full run, downloads
  uv run python backend/scripts/harvest_resources.py --dry     # crawl + classify only
  uv run python backend/scripts/harvest_resources.py --only spellbee
"""
from __future__ import annotations

import argparse
import asyncio
import json
import re
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from backend.app.scraper.client import scraper_session  # noqa: E402
from backend.app.scraper import resources as R  # noqa: E402


# Expected-freq + sync-tier routing. First match wins.
FREQ_RULES: list[tuple[re.Pattern[str], str, str]] = [
    (re.compile(r"daily.?bulletin|announcement", re.I),     "daily",   "light"),
    (re.compile(r"news.?letter|magazine|insights|event",re.I),"weekly", "medium"),
    (re.compile(r"quiz", re.I),                             "monthly", "heavy"),
    (re.compile(r"time.?table|homework.?schedule|lesson.?timing", re.I), "termly", "heavy"),
    (re.compile(r"assessment|exam|cbse", re.I),             "termly",  "heavy"),
    (re.compile(r"spell|bee|vocab|word.?list|book.?list|reading.?list", re.I), "termly", "heavy"),
    (re.compile(r"syllabus", re.I),                         "annual",  "heavy"),
    (re.compile(r"handbook|id.?card|calendar|parent.?rep|prefect|uniform|book.?shop|directory|counsel|fee", re.I), "annual", "manual"),
]


def _freq_tier(title: str) -> tuple[str, str]:
    for rx, freq, tier in FREQ_RULES:
        if rx.search(title):
            return freq, tier
    return "unknown", "manual"


def _load_children() -> list[dict]:
    conn = sqlite3.connect(str(ROOT / "data" / "app.db"))
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            "SELECT id, display_name, class_level, class_section FROM children ORDER BY id"
        ).fetchall()
    finally:
        conn.close()
    return [dict(r) for r in rows]


class _ChildRow:
    """Duck-typed child object matching the `_ChildLike` protocol used by paths.py."""
    def __init__(self, row: dict):
        self.id = row["id"]
        self.display_name = row["display_name"]
        self.class_level = row["class_level"]
        self.class_section = row["class_section"]


async def main(dry: bool, only: str | None) -> int:
    children_rows = _load_children()
    children = [_ChildRow(r) for r in children_rows]
    print(f"children: {[(c.id, c.display_name, f'{c.class_level}{c.class_section}') for c in children]}")

    async with scraper_session() as client:
        tiles = await R.harvest_home_tiles(client)
        print(f"found {len(tiles)} home tiles")
        expanded = []
        for t in tiles:
            if t.kind == "portal-page":
                try:
                    expanded.extend(await R.expand_portal_page(client, t))
                except Exception as e:
                    print(f"  ! expand failed for {t.title!r}: {e}")
        all_tiles = tiles + expanded
        print(f"{len(all_tiles)} total after one-hop expansion")
        print()

        # Classify + filter
        plan = []
        for t in all_tiles:
            freq, tier = _freq_tier(t.title)
            plan.append({
                "title": t.title,
                "url": t.resolved_url,
                "kind": t.kind,
                "category": t.category,
                "schoolwide": t.schoolwide,
                "freq": freq,
                "tier": tier,
            })

        if only:
            plan = [p for p in plan if p["category"] == only or p["freq"] == only or p["tier"] == only]
            print(f"filter --only={only!r}: {len(plan)} tile(s)")

        # Print a table
        print(f"  {'TITLE':40}  {'KIND':12}  {'CAT':11}  {'FREQ':8}  {'TIER':6}  URL")
        print(f"  {'-'*40}  {'-'*12}  {'-'*11}  {'-'*8}  {'-'*6}  ---")
        for p in plan[:80]:
            print(f"  {p['title'][:40]:40}  {p['kind']:12}  {p['category']:11}  {p['freq']:8}  {p['tier']:6}  {p['url'][:70]}")

        saved = []
        skipped = []
        if not dry:
            print()
            print("=== downloading files")
            for p, t in zip(plan, (t for t in all_tiles if not only or {"title": t.title, "url": t.resolved_url, "kind": t.kind, "category": t.category, "schoolwide": t.schoolwide} in plan or True)):
                # Use the actual tile object for download
                pass
            # simpler: just iterate the original tile list, filtered same way
            for t in all_tiles:
                if only:
                    freq_t, tier_t = _freq_tier(t.title)
                    if t.category != only and freq_t != only and tier_t != only:
                        continue
                try:
                    fetched = await R.fetch_tile(client, t)
                except Exception as e:
                    skipped.append({"title": t.title, "url": t.resolved_url, "reason": f"fetch-exc: {e}"})
                    continue
                if fetched is None:
                    skipped.append({"title": t.title, "url": t.resolved_url, "kind": t.kind, "reason": "non-file"})
                    continue
                body, ctype, suggested = fetched
                try:
                    paths = await R.save_for_children(body, ctype, suggested, t, children)
                except Exception as e:
                    skipped.append({"title": t.title, "url": t.resolved_url, "reason": f"save-exc: {e}"})
                    continue
                freq, tier = _freq_tier(t.title)
                saved.append({
                    "title": t.title,
                    "url": t.resolved_url,
                    "kind": t.kind,
                    "category": t.category,
                    "schoolwide": t.schoolwide,
                    "freq": freq, "tier": tier,
                    "paths": [str(p) for p in paths],
                    "bytes": len(body),
                    "content_type": ctype,
                })
                print(f"  ✓ {t.title[:50]:50} {len(body):>9}B  → {paths[0]}")

        # Report
        report_path = ROOT / "data" / "resources_report.json"
        report_path.write_text(json.dumps({
            "plan": plan,
            "saved": saved,
            "skipped": skipped,
        }, indent=2))
        print()
        print(f"report: {report_path.relative_to(ROOT)}")
        print(f"saved: {len(saved)}   skipped: {len(skipped)}")
        return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry", action="store_true", help="crawl + classify only, don't download")
    ap.add_argument("--only", default=None, help="filter by category / freq / tier (e.g. spellbee, weekly, heavy)")
    args = ap.parse_args()
    sys.exit(asyncio.run(main(args.dry, args.only)))
