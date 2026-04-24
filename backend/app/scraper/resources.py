"""Resource-page harvester for the parent portal.

The existing scraper ignores the portal landing page entirely — it only
walks the planner, grade reports, and assignment detail pages. The home
page, however, has a sidebar of `.icon-block` tiles linking to all the
school-wide and class-independent PDFs (Spelling List, Book List,
Timetables, Homework Schedules, Newsletter, Handbook, etc.).

This module:
  1. Opens the authenticated portal home and harvests every `.icon-block`
     + `a[href]` tile.
  2. Classifies each by keyword heuristic (spellbee / schedule / reading /
     newsletter / handbook / misc).
  3. For portal-internal `/pages/<slug>` targets, recursively follows one
     hop to collect the PDFs they embed.
  4. Downloads every resulting file — direct URLs are pulled with the
     Playwright request context; Google Drive links are resolved via the
     `uc?export=download&id=<id>` endpoint and the virus-warning form
     workaround.
  5. Writes each file into the per-kid `rawdata/<kid>/<category>/` dir
     (or `rawdata/schoolwide/<category>/` for kid-independent resources),
     with a slugified human-readable name.

Intended to run from the heavy-tier weekly sync or on demand.
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from ..config import REPO_ROOT
from ..util import paths as P

log = logging.getLogger(__name__)


PORTAL_HOME = "https://portals.veracross.eu/vasantvalleyschool/parent"
PORTAL_HOSTS = {"portals.veracross.eu", "portals-embed.veracross.eu", "documents.veracross.eu"}

# Category routing — first match wins. Rule: (name_regex, kid_dir_name, is_schoolwide).
# is_schoolwide=True means save under data/rawdata/schoolwide/<dir>/ instead of per-kid.
CATEGORY_RULES: list[tuple[re.Pattern[str], str, bool]] = [
    (re.compile(r"spell|bee|vocab|word.?list", re.I), "spellbee", False),
    (re.compile(r"reading|book.?list", re.I), "reading", False),
    (re.compile(r"time.?table|homework.?schedule|lesson.?timing", re.I), "schedules", True),
    (re.compile(r"assessment|exam|cbse", re.I), "assessments", True),
    (re.compile(r"newsletter|bulletin|magazine|insights", re.I), "news", True),
    (re.compile(r"handbook|id.?card|fee|parent.?rep|prefect", re.I), "general", True),
    (re.compile(r"syllabus", re.I), "syllabus", False),
]


@dataclass(frozen=True)
class ResourceTile:
    title: str
    href: str                # as seen in the home page
    resolved_url: str        # absolute URL
    category: str            # e.g. 'spellbee'
    schoolwide: bool
    kind: str                # 'drive' | 'portal-page' | 'direct-file' | 'external-html' | 'unknown'

    @property
    def drive_file_id(self) -> str | None:
        if self.kind != "drive":
            return None
        # Any Google Docs / Sheets / Slides / Drive URL encodes the file-id
        # as either `/file/d/<id>/`, `/spreadsheets/d/<id>/`,
        # `/document/d/<id>/`, `/presentation/d/<id>/`, or `?id=<id>`.
        for rx in (
            r"/(?:file|spreadsheets|document|presentation|forms)/d/([^/?#]+)",
            r"[?&]id=([^&]+)",
        ):
            m = re.search(rx, self.resolved_url)
            if m:
                return m.group(1)
        return None


def _classify(title: str) -> tuple[str, bool]:
    for rx, cat, schoolwide in CATEGORY_RULES:
        if rx.search(title):
            return cat, schoolwide
    return "misc", True


def _kind_of(url: str) -> str:
    host = urlparse(url).netloc.lower()
    if "drive.google.com" in host:
        return "drive"
    if "docs.google.com" in host and any(p in url for p in ("/spreadsheets/", "/document/", "/presentation/")):
        return "drive"
    if host in PORTAL_HOSTS:
        if "/pages/" in url:
            return "portal-page"
        if re.search(r"\.(pdf|docx?|pptx?|xlsx?|png|jpe?g)(\?|$)", url, re.I):
            return "direct-file"
        return "portal-other"
    if re.search(r"\.(pdf|docx?|pptx?|xlsx?|png|jpe?g)(\?|$)", url, re.I):
        return "direct-file"
    return "external-html"


# ─── harvesting ─────────────────────────────────────────────────────────────

async def harvest_home_tiles(client) -> list[ResourceTile]:
    """Extract every `.icon-block` style tile from the portal home."""
    page = client._page  # pylint: disable=protected-access
    await page.goto(PORTAL_HOME, wait_until="networkidle", timeout=60_000)
    await page.wait_for_timeout(4000)  # sidebar hydrates on a delay
    rows = await page.evaluate("""
        () => {
          const out = [];
          document.querySelectorAll('a.icon-block, a[href].card, a[href].menu-item, a[href].section-tile').forEach(el => {
            const t = (el.innerText || '').trim();
            const h = el.getAttribute('href') || '';
            if (t && h) out.push({title: t, href: h});
          });
          return out;
        }
    """)
    tiles: list[ResourceTile] = []
    seen_urls: set[str] = set()
    for r in rows:
        title = (r["title"] or "").split("\n", 1)[0].strip()[:120]
        href = r["href"]
        abs_url = urljoin(PORTAL_HOME, href)
        if abs_url in seen_urls:
            continue
        seen_urls.add(abs_url)
        category, schoolwide = _classify(title)
        tiles.append(ResourceTile(
            title=title,
            href=href,
            resolved_url=abs_url,
            category=category,
            schoolwide=schoolwide,
            kind=_kind_of(abs_url),
        ))
    return tiles


async def expand_portal_page(client, tile: ResourceTile) -> list[ResourceTile]:
    """Follow a portal `/pages/<slug>` link one hop and harvest any document
    anchors on that page. The returned ResourceTile entries inherit the
    parent's category + schoolwide flag."""
    page = client._page  # pylint: disable=protected-access
    await page.goto(tile.resolved_url, wait_until="networkidle", timeout=45_000)
    await page.wait_for_timeout(1500)
    html = await page.content()
    soup = BeautifulSoup(html, "lxml")
    found: list[ResourceTile] = []
    seen_urls: set[str] = set()
    for a in soup.select("a[href]"):
        href = (a.get("href") or "").strip()
        if not href or href.startswith(("#", "mailto:", "javascript:")):
            continue
        abs_url = urljoin(tile.resolved_url, href)
        if abs_url == tile.resolved_url or abs_url in seen_urls:
            continue
        seen_urls.add(abs_url)
        kind = _kind_of(abs_url)
        if kind in ("drive", "direct-file"):
            t = a.get_text(" ", strip=True) or abs_url.rsplit("/", 1)[-1]
            found.append(ResourceTile(
                title=t[:120], href=href, resolved_url=abs_url,
                category=tile.category, schoolwide=tile.schoolwide,
                kind=kind,
            ))
    return found


# ─── downloading ────────────────────────────────────────────────────────────

async def _download_direct(client, url: str) -> tuple[bytes, str | None, str]:
    """Returns (body, content_type, suggested_filename)."""
    resp = await client._ctx.request.get(url, timeout=60_000)  # pylint: disable=protected-access
    if resp.status != 200:
        raise RuntimeError(f"HTTP {resp.status} for {url}")
    ctype = resp.headers.get("content-type") or ""
    body = await resp.body()
    # Try to pull filename from Content-Disposition; fallback to URL tail.
    cd = resp.headers.get("content-disposition", "")
    m = re.search(r'filename\*?=(?:UTF-8\'\')?"?([^";]+)"?', cd, re.I)
    name = m.group(1) if m else url.rsplit("/", 1)[-1].split("?", 1)[0]
    return body, ctype, name


async def _download_drive(client, file_id: str, source_url: str = "") -> tuple[bytes, str | None, str]:
    """Download a public-link Google Drive file. Handles the virus-warning
    interstitial that Drive shows for medium-large files. For native
    Sheets/Docs/Slides URLs we can't go through /uc?export=download — those
    require the per-format export endpoint on `docs.google.com`."""
    # Native Google doc types → use their export endpoints (yield real bytes).
    if source_url:
        if "/spreadsheets/d/" in source_url:
            url1 = f"https://docs.google.com/spreadsheets/d/{file_id}/export?format=xlsx"
            body, ctype, name = await _download_direct(client, url1)
            if not name or name.startswith("http"):
                name = f"spreadsheet_{file_id}.xlsx"
            return body, ctype, name
        if "/document/d/" in source_url:
            url1 = f"https://docs.google.com/document/d/{file_id}/export?format=pdf"
            body, ctype, name = await _download_direct(client, url1)
            if not name or name.startswith("http"):
                name = f"document_{file_id}.pdf"
            return body, ctype, name
        if "/presentation/d/" in source_url:
            url1 = f"https://docs.google.com/presentation/d/{file_id}/export/pdf"
            body, ctype, name = await _download_direct(client, url1)
            if not name or name.startswith("http"):
                name = f"slides_{file_id}.pdf"
            return body, ctype, name
    # Generic Drive file — standard export=download with virus-warning shim.
    url1 = f"https://drive.google.com/uc?export=download&id={file_id}"
    ctx = client._ctx  # pylint: disable=protected-access
    resp = await ctx.request.get(url1, timeout=60_000, max_redirects=5)
    body = await resp.body()
    ctype = resp.headers.get("content-type") or ""
    # If we got HTML, Drive is showing the confirmation interstitial.
    if "text/html" in ctype and len(body) < 100_000:
        html = body.decode("utf-8", "ignore")
        # Look for the confirm form or the confirm token
        m_confirm = re.search(r'name="confirm"\s+value="([^"]+)"', html)
        m_uuid = re.search(r'name="uuid"\s+value="([^"]+)"', html)
        m_form = re.search(r'action="(https://[^"]*drive[^"]*download[^"]*)"', html)
        if m_confirm and m_form:
            confirm = m_confirm.group(1)
            uuid = m_uuid.group(1) if m_uuid else ""
            action = m_form.group(1).replace("&amp;", "&")
            sep = "&" if "?" in action else "?"
            url2 = f"{action}{sep}id={file_id}&export=download&confirm={confirm}"
            if uuid:
                url2 += f"&uuid={uuid}"
            resp = await ctx.request.get(url2, timeout=90_000, max_redirects=5)
            body = await resp.body()
            ctype = resp.headers.get("content-type") or ""
    cd = resp.headers.get("content-disposition", "")
    m = re.search(r'filename\*?=(?:UTF-8\'\')?"?([^";]+)"?', cd, re.I)
    name = m.group(1) if m else f"drive_{file_id}.bin"
    if name.startswith("drive_") and "pdf" in ctype:
        name = f"drive_{file_id}.pdf"
    return body, ctype, name


def _dest_path(tile: ResourceTile, filename: str, child: Any | None = None) -> Path:
    """Where does `tile`'s file land on disk?

    Schoolwide → data/rawdata/schoolwide/<category>/<filename>
    Per-kid    → data/rawdata/<kid_slug>/<category>/<filename>  (caller
                 picks which kid; for spellbee/reading we'd save per-kid
                 for every kid if schoolwide=False — this helper only
                 resolves ONE destination at a time)."""
    root = P.rawdata_root()
    if tile.schoolwide or child is None:
        base = root / "schoolwide" / tile.category
    else:
        base = P.kid_root(child) / tile.category
    base.mkdir(parents=True, exist_ok=True)
    return base / filename


def _safe_filename(name: str) -> str:
    name = name.strip().replace("/", "_").replace("\\", "_")
    name = re.sub(r"[^\w\.\- ]", "_", name)
    return name[:180] or "file.bin"


async def fetch_tile(client, tile: ResourceTile) -> tuple[bytes, str | None, str] | None:
    if tile.kind == "drive":
        fid = tile.drive_file_id
        if not fid:
            log.warning("drive tile with no file_id: %s", tile.resolved_url)
            return None
        try:
            return await _download_drive(client, fid, source_url=tile.resolved_url)
        except Exception as e:
            log.warning("drive fetch failed for %s (%s): %s", tile.title, fid, e)
            return None
    if tile.kind in ("direct-file",):
        try:
            return await _download_direct(client, tile.resolved_url)
        except Exception as e:
            log.warning("direct fetch failed for %s: %s", tile.resolved_url, e)
            return None
    return None  # portal-page / external-html are not file downloads


async def save_for_children(
    body: bytes, ctype: str | None, suggested: str,
    tile: ResourceTile, children: list[Any],
) -> list[Path]:
    """Write `body` to either data/rawdata/schoolwide/<cat>/ or per-kid
    dirs. Returns the list of paths written."""
    safe = _safe_filename(suggested)
    # If the filename has no extension but we can infer one from content-type,
    # tack it on.
    if "." not in safe[-6:] and ctype:
        if "pdf" in ctype: safe += ".pdf"
        elif "png" in ctype: safe += ".png"
        elif "jpeg" in ctype: safe += ".jpg"
    out: list[Path] = []
    if tile.schoolwide or not children:
        dst = _dest_path(tile, safe, child=None)
        dst.write_bytes(body)
        out.append(dst)
    else:
        for c in children:
            dst = _dest_path(tile, safe, child=c)
            dst.write_bytes(body)
            out.append(dst)
    return out


# ─── top-level entry ────────────────────────────────────────────────────────

async def harvest_all(client, children: list[Any]) -> dict[str, Any]:
    """Find every tile, expand portal-pages one level, download everything
    classifiable, and return a summary."""
    tiles = await harvest_home_tiles(client)
    log.info("harvest: %d tiles from portal home", len(tiles))

    # Expand portal-page tiles one hop so their embedded PDFs are picked up.
    expanded: list[ResourceTile] = []
    for t in tiles:
        if t.kind == "portal-page":
            try:
                expanded.extend(await expand_portal_page(client, t))
            except Exception as e:
                log.warning("expand failed for %s: %s", t.title, e)
    all_tiles = tiles + expanded
    log.info("harvest: %d total after expansion", len(all_tiles))

    saved: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    for t in all_tiles:
        try:
            fetched = await fetch_tile(client, t)
        except Exception as e:
            log.warning("fetch error: %s — %s", t.title, e)
            fetched = None
        if fetched is None:
            skipped.append({"title": t.title, "url": t.resolved_url, "kind": t.kind, "reason": "not-a-file"})
            continue
        body, ctype, suggested = fetched
        try:
            paths = await save_for_children(body, ctype, suggested, t, children)
        except Exception as e:
            log.warning("save error for %s: %s", t.title, e)
            skipped.append({"title": t.title, "url": t.resolved_url, "kind": t.kind, "reason": str(e)})
            continue
        saved.append({
            "title": t.title,
            "url": t.resolved_url,
            "kind": t.kind,
            "category": t.category,
            "schoolwide": t.schoolwide,
            "paths": [P.repo_relative(p) for p in paths],
            "bytes": len(body),
            "content_type": ctype,
        })
    return {"tiles": len(all_tiles), "saved": saved, "skipped": skipped}
