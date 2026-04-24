"""Dump the per-student Classes & Reports overview page so we can see
how Veracross links to individual classes + their documents tab.

Writes data/diagnostics/student_<id>.html + _links.json for each child.
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from urllib.parse import urljoin

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

STUDENT_IDS = ["103460", "103609"]  # from home page "Classes & Reports" links
BASE = "https://portals.veracross.eu/vasantvalleyschool/parent"


async def main() -> int:
    from backend.app.scraper.client import scraper_session

    out = ROOT / "data" / "diagnostics"
    out.mkdir(parents=True, exist_ok=True)
    async with scraper_session() as client:
        page = client._page
        for sid in STUDENT_IDS:
            url = f"{BASE}/student/{sid}/overview"
            print(f"→ {url}")
            await page.goto(url, wait_until="networkidle", timeout=45_000)
            await page.wait_for_timeout(4000)
            html = await page.content()
            (out / f"student_{sid}.html").write_text(html, encoding="utf-8")
            print(f"  wrote {len(html):,}B")
            links = await page.evaluate("""
                () => {
                  const out = [];
                  document.querySelectorAll('a[href]').forEach(el => {
                    const t = (el.innerText || '').trim().slice(0, 100);
                    out.push({text: t, href: el.getAttribute('href') || '', cls: (el.className||'').toString().slice(0,60)});
                  });
                  return out;
                }
            """)
            (out / f"student_{sid}_links.json").write_text(json.dumps(links, indent=2))
            print(f"  {len(links)} anchors")
            # Print likely class tabs
            print(f"  class-ish anchors (first 40):")
            for l in links:
                h = l["href"]
                if "/classes/" in h or "/class/" in h or "gradebook" in h or "assignment" in h or "document" in h:
                    print(f"    [{l['text'][:40]:40}] {h[:120]}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
