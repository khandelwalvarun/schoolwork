"""Portal explorer — uses the authenticated scraper session to find
anything resembling Spelling Bee lists that the regular scraper never
visits.

Strategy:
  1. Load the parent portal home; print sidebar / nav links.
  2. For each class_id we know about, try common class-page URLs
     (website, documents, resources, announcements, files) and dump
     any PDF/image/doc links found.
  3. Spider BFS up to depth 2 from the portal home, staying same-domain,
     collecting every link whose href matches a doc extension OR whose
     text contains 'spell' / 'bee' / 'list' / 'word'.
  4. Dump a flat report (stdout + JSON).

Run: uv run python backend/scripts/explore_portal.py
Optional: --depth 3 for wider spider; --save to download promising files.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from collections import deque
from pathlib import Path
from urllib.parse import urldefrag, urljoin, urlparse

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from backend.app.scraper.client import scraper_session  # noqa: E402
from backend.app.scraper.attachments import DOC_EXT_RE, ATTACHMENT_HOST_RE, extract_attachment_links  # noqa: E402


PORTAL_HOSTS = {"portals.veracross.eu", "portals-embed.veracross.eu", "documents.veracross.eu"}
BASE = "https://portals.veracross.eu/vasantvalleyschool/parent"
EMBED = "https://portals-embed.veracross.eu/vasantvalleyschool/parent"


SPELLISH = re.compile(r"(spell|bee|vocab|word\s*list)", re.I)


async def main(depth: int, save: bool) -> int:
    async with scraper_session() as client:
        print(f"=== home: {BASE}")
        home_html = await client.get_html(BASE)
        print(f"bytes: {len(home_html)}")

        # Top-level nav
        from bs4 import BeautifulSoup
        s = BeautifulSoup(home_html, "lxml")
        nav_links: list[tuple[str, str]] = []
        for a in s.select("a[href]"):
            href = (a.get("href") or "").strip()
            if not href or href.startswith(("#", "mailto:", "javascript:")):
                continue
            # Only in-portal
            parsed = urlparse(urljoin(BASE, href))
            if parsed.netloc and parsed.netloc not in PORTAL_HOSTS:
                continue
            text = a.get_text(" ", strip=True)
            if text:
                nav_links.append((text, urljoin(BASE, href)))
        # dedup by url
        seen = set()
        dedup_nav = []
        for t, u in nav_links:
            u2, _ = urldefrag(u)
            if u2 in seen:
                continue
            seen.add(u2)
            dedup_nav.append((t, u2))
        print(f"\nnav links ({len(dedup_nav)}):")
        for t, u in dedup_nav[:60]:
            marker = " 🎯" if SPELLISH.search(t) else ""
            print(f"  [{t[:40]:40}] {u}{marker}")

        # Class pages — try the known patterns for the 4C English class
        CLASS_IDS = {
            "4C English":        "6098",
            "4C Hindi":          "6117",
            "4C Mathematics":    "6163",
            "4C Science":        "12507",
            "4C Social Science": "12501",
            "6B English":        "6055",  # guess; we'll also try via planner
        }
        # Also grab class_ids from DB
        import sqlite3
        conn = sqlite3.connect(str(ROOT / "data" / "app.db"))
        try:
            rows = conn.execute("""
                SELECT DISTINCT subject, json_extract(raw_json, '$.row_id') rid
                FROM veracross_items WHERE kind='assignment' AND rid IS NOT NULL
            """).fetchall()
        finally:
            conn.close()
        class_map: dict[str, str] = dict(rows)
        class_map.update(CLASS_IDS)
        print(f"\nclasses: {class_map}")

        candidates_per_class = [
            "/classes/{cid}",
            "/classes/{cid}/website",
            "/classes/{cid}/documents",
            "/classes/{cid}/announcements",
            "/classes/{cid}/files",
            "/classes/{cid}/resources",
        ]

        all_docs: list[dict] = []

        async def try_page(url: str, source: str) -> str | None:
            try:
                html = await client.get_html(url)
            except Exception as e:
                print(f"  ✗ {url} — {e}")
                return None
            if not html:
                return None
            attachments = extract_attachment_links(html)
            for a in attachments:
                all_docs.append({"source": source, "page": url, **a})
            # also grab any link whose text looks spelling-bee-ish
            s2 = BeautifulSoup(html, "lxml")
            for a in s2.select("a[href]"):
                t = a.get_text(" ", strip=True)
                h = (a.get("href") or "").strip()
                if SPELLISH.search(t) or SPELLISH.search(h):
                    all_docs.append({
                        "source": source + ":spellish",
                        "page": url,
                        "filename": t[:80],
                        "url": urljoin(url, h),
                    })
            return html

        # Class-level sweeps
        print("\n=== class-level pages")
        for subj, cid in class_map.items():
            for pat in candidates_per_class:
                url = EMBED + pat.format(cid=cid)
                await try_page(url, f"class:{subj}")
            # also main-portal variants
            url = BASE + f"/classes/{cid}"
            await try_page(url, f"class-main:{subj}")

        # BFS from nav links up to depth
        print(f"\n=== BFS depth={depth} from nav")
        visited: set[str] = set()
        q: deque[tuple[str, int]] = deque()
        for _, u in dedup_nav:
            if u not in visited:
                q.append((u, 0))
                visited.add(u)

        budget = 40  # hard cap
        while q and budget > 0:
            url, d = q.popleft()
            budget -= 1
            html = await try_page(url, f"bfs:d={d}")
            if html is None or d >= depth:
                continue
            s3 = BeautifulSoup(html, "lxml")
            for a in s3.select("a[href]"):
                href = (a.get("href") or "").strip()
                if not href or href.startswith(("#", "mailto:", "javascript:")):
                    continue
                next_url = urljoin(url, href)
                next_url, _ = urldefrag(next_url)
                if urlparse(next_url).netloc not in PORTAL_HOSTS:
                    continue
                if next_url in visited:
                    continue
                visited.add(next_url)
                q.append((next_url, d + 1))

        # Dedup docs by url
        seen2 = set()
        dedup_docs = []
        for d in all_docs:
            k = d.get("url", "")
            if k in seen2:
                continue
            seen2.add(k)
            dedup_docs.append(d)

        print(f"\n=== {len(dedup_docs)} unique doc-like links found")
        spellish_only = [d for d in dedup_docs if SPELLISH.search(d.get("filename", "") + " " + d.get("url", "") + " " + d.get("page", ""))]
        print(f"    {len(spellish_only)} match spell/bee/vocab/wordlist heuristic")

        for d in dedup_docs:
            mark = " 🎯" if d in spellish_only else ""
            fn = (d.get("filename", "") or "")[:60]
            print(f"  [{d['source']:30}] {fn:60} ← {d['url'][:120]}{mark}")

        # Dump JSON for programmatic follow-up
        report_path = ROOT / "data" / "explore_report.json"
        report_path.write_text(json.dumps({
            "total_docs": len(dedup_docs),
            "spellish": spellish_only,
            "all": dedup_docs,
            "visited_pages": sorted(visited)[:100],
        }, indent=2))
        print(f"\nreport written to {report_path.relative_to(ROOT)}")

        if save and spellish_only:
            from backend.app.scraper.attachments import _fetch_bytes
            stash = ROOT / "data" / "explore_stash"
            stash.mkdir(parents=True, exist_ok=True)
            for i, d in enumerate(spellish_only):
                try:
                    body, ctype = await _fetch_bytes(client, d["url"])
                    ext = ".pdf" if "pdf" in (ctype or "") else ".bin"
                    (stash / f"spellish_{i:02d}{ext}").write_bytes(body)
                    print(f"  saved {len(body)}B → data/explore_stash/spellish_{i:02d}{ext}")
                except Exception as e:
                    print(f"  ✗ {d['url']}: {e}")

        return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--depth", type=int, default=2)
    ap.add_argument("--save", action="store_true", help="download the promising hits to data/explore_stash/")
    args = ap.parse_args()
    sys.exit(asyncio.run(main(args.depth, args.save)))
