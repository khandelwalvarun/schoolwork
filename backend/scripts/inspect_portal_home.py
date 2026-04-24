"""Dump the parent-portal landing page so we can see exactly what
structure wraps sections like 'Spelling List', 'Book List 2026-27',
'Newsletter' that the existing spider missed.

Writes three artefacts under data/diagnostics/:
  - home.html                — the rendered HTML as Playwright sees it
  - home_text.txt            — pure text with line breaks (for human scan)
  - home_links.json          — every element that could be a nav target:
                                 <a href>, role=link, [onclick], [data-href],
                                 [data-url], buttons, etc.

Then prints a short diff of SIDEBAR_HITS — sections the user named that
we DID find vs didn't.
"""
from __future__ import annotations

import asyncio
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))


USER_SECTIONS = [
    "Assessments and Examinations",
    "Assessment Syllabus",
    "Assessment schedule",
    "Class 12 CBSE Examination 2026",
    "Class 10 CBSE Examination 2026",
    "Reading and Resources",
    "Newsletter",
    "Science Magazine",
    "Library Magazine",
    "Spelling List",
    "Book List 2026-27",
    "Reading Lists 2025",
    "Syllabus",
    "General Awareness Quiz Jr.",
    "General Awareness Quiz Sr.",
    "Schedules and Venues",
    "Zoom Links",
    "Sr. School Time Table",
    "Jr. School Time Table",
    "Jr. School Homework Schedule",
    "Sr. School Homework Schedule",
    "My Household",
    "School Fee",
    "My Calendar",
    "Parent & Escort ID Card Form",
    "BREAKFAST AND LUNCH MENU",
    "Uniform Shop",
    "Book Shop",
    "Career and College Counselling",
    "Faculty/Staff Directory",
    "Parent Reps",
    "Prefect Council",
    "DAILY BULLETIN",
    "School Calendar",
    "Student Handbook",
]


async def main() -> int:
    from backend.app.scraper.client import scraper_session

    out_dir = ROOT / "data" / "diagnostics"
    out_dir.mkdir(parents=True, exist_ok=True)

    async with scraper_session() as client:
        # Direct page access so we can wait longer for client-side render
        page = client._page  # pylint: disable=protected-access
        BASE = "https://portals.veracross.eu/vasantvalleyschool/parent"
        print(f"→ {BASE}")
        await page.goto(BASE, wait_until="networkidle", timeout=60_000)
        # Extra wait — the sidebar hydrates on a delay
        await page.wait_for_timeout(5000)

        html = await page.content()
        (out_dir / "home.html").write_text(html, encoding="utf-8")
        print(f"wrote home.html — {len(html):,} bytes")

        text = await page.evaluate("() => document.body.innerText || document.body.textContent")
        (out_dir / "home_text.txt").write_text(text, encoding="utf-8")
        print(f"wrote home_text.txt — {len(text):,} chars")

        # Harvest every navigable element.
        links = await page.evaluate("""
            () => {
              const out = [];
              const sel = 'a[href], [role="link"], [onclick], [data-href], [data-url], button[data-href], button[data-url], a.card, .card a, .section-tile, .menu-item';
              document.querySelectorAll(sel).forEach(el => {
                const rect = el.getBoundingClientRect();
                if (rect.width === 0 && rect.height === 0) return;
                const href = el.getAttribute('href') || el.getAttribute('data-href') || el.getAttribute('data-url') || '';
                const onclick = el.getAttribute('onclick') || '';
                out.push({
                  tag: el.tagName.toLowerCase(),
                  text: (el.innerText || '').trim().slice(0, 120),
                  href,
                  onclick: onclick.slice(0, 160),
                  cls: (el.className || '').toString().slice(0, 80),
                  role: el.getAttribute('role') || '',
                });
              });
              return out;
            }
        """)
        (out_dir / "home_links.json").write_text(json.dumps(links, indent=2), encoding="utf-8")
        print(f"wrote home_links.json — {len(links)} entries")

        # Match which user-named sections we can find in the text
        hits = {}
        for name in USER_SECTIONS:
            hits[name] = name.lower() in text.lower()
        found = sum(1 for v in hits.values() if v)
        print()
        print(f"user-named sections present in home text: {found}/{len(USER_SECTIONS)}")
        for k, v in hits.items():
            print(f"  {'✓' if v else '✗'}  {k}")

        # For each section we found, try to locate the enclosing link/button
        # and print its href or onclick so we know where it leads.
        print()
        print("Link targets for each found section:")
        target_info = await page.evaluate("""
            (names) => {
              const out = {};
              for (const name of names) {
                const lower = name.toLowerCase();
                const match = [...document.querySelectorAll('*')].find(
                  e => e.innerText && e.innerText.trim().toLowerCase() === lower && e.children.length === 0
                );
                if (!match) { out[name] = null; continue; }
                // walk up to find an anchor / clickable
                let cur = match;
                for (let i = 0; i < 6 && cur; i++, cur = cur.parentElement) {
                  if (cur.tagName === 'A' && cur.getAttribute('href')) {
                    out[name] = { kind: 'a', href: cur.getAttribute('href'), cls: cur.className };
                    break;
                  }
                  if (cur.hasAttribute('onclick') || cur.hasAttribute('data-href') || cur.hasAttribute('data-url')) {
                    out[name] = {
                      kind: cur.tagName.toLowerCase(),
                      href: cur.getAttribute('href') || cur.getAttribute('data-href') || cur.getAttribute('data-url') || '',
                      onclick: (cur.getAttribute('onclick') || '').slice(0, 200),
                      cls: cur.className,
                    };
                    break;
                  }
                }
                if (!out[name]) out[name] = { kind: 'orphan', parentTag: (match.parentElement?.tagName || ''), cls: match.parentElement?.className || '' };
              }
              return out;
            }
        """, [n for n, v in hits.items() if v])
        (out_dir / "section_targets.json").write_text(json.dumps(target_info, indent=2), encoding="utf-8")
        for name, info in target_info.items():
            print(f"  {name}: {info}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
