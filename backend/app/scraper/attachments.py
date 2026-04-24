"""Find + download attachments from assignment / message detail HTML.

Uses the authenticated Playwright request context so Veracross's JWT-signed
`files2.veracross.com/.../download?auth=…` links return real bytes, not a
redirect to the login page.

Saves files under `data/attachments/` keyed by SHA-256 (dedups across items).
"""
from __future__ import annotations

import hashlib
import logging
import mimetypes
import re
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

from bs4 import BeautifulSoup
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import REPO_ROOT, get_settings
from ..models import Attachment, Child, VeracrossItem
from ..util import paths as P

log = logging.getLogger(__name__)

# Hosts we trust as attachment sources on the Veracross platform.
ATTACHMENT_HOST_RE = re.compile(
    r"(files\d*\.veracross\.com|files-cdn\.veracross|documents\.veracross|vxfs|blob\.core)"
)
# Anchors with these in the href/text are likely real attachments (vs nav links).
DOC_EXT_RE = re.compile(
    r"\.(pdf|docx?|pptx?|xlsx?|png|jpe?g|gif|webp|mp3|mp4|mov|zip|rar|7z|csv|txt|rtf)(\?|$)",
    re.I,
)


def extract_attachment_links(html: str, base_url: str = "") -> list[dict[str, str]]:
    """Return [{url, filename}] for plausible attachment anchors in the HTML."""
    if not html:
        return []
    soup = BeautifulSoup(html, "lxml")
    out: list[dict[str, str]] = []
    seen: set[str] = set()
    for a in soup.select("a[href]"):
        href = (a.get("href") or "").strip()
        if not href or href.startswith(("#", "mailto:", "javascript:")):
            continue
        # Make absolute if needed.
        if href.startswith("//"):
            href = "https:" + href
        # Heuristics: trusted host OR file-extension match.
        is_trusted_host = bool(ATTACHMENT_HOST_RE.search(href))
        looks_like_file = bool(DOC_EXT_RE.search(href))
        if not (is_trusted_host or looks_like_file):
            continue
        if href in seen:
            continue
        seen.add(href)
        # Prefer anchor text if it looks like a filename; otherwise infer from URL.
        text = a.get_text(" ", strip=True) or ""
        fname = text if ("." in text and len(text) < 200) else _filename_from_url(href)
        out.append({"url": href, "filename": fname or "attachment.bin"})
    return out


def _filename_from_url(url: str) -> str:
    try:
        p = urlparse(url)
        last = unquote(p.path.rsplit("/", 1)[-1])
        return last or "attachment.bin"
    except Exception:
        return "attachment.bin"


def _guess_ext(filename: str, mime: str | None) -> str:
    ext = Path(filename).suffix.lower()
    if ext:
        return ext
    if mime:
        guessed = mimetypes.guess_extension(mime)
        if guessed:
            return guessed
    return ""


async def _fetch_bytes(client, url: str) -> tuple[bytes, str | None]:
    """Download `url` with the authenticated context's request API.
    Returns (body_bytes, content_type)."""
    response = await client._ctx.request.get(url, timeout=60_000)
    body = await response.body()
    ctype = response.headers.get("content-type")
    if response.status != 200:
        raise RuntimeError(f"HTTP {response.status} for {url}")
    return body, ctype


async def _load_child_and_item(
    session: AsyncSession, item_id: int, child_id: int | None,
) -> tuple[Child | None, VeracrossItem | None]:
    """Fetch Child + VeracrossItem rows we need to compose the human-readable
    filename and locate the per-kid attachments directory."""
    item = (
        await session.execute(select(VeracrossItem).where(VeracrossItem.id == item_id))
    ).scalar_one_or_none()
    child_pk = child_id or (item.child_id if item else None)
    child: Child | None = None
    if child_pk is not None:
        child = (
            await session.execute(select(Child).where(Child.id == child_pk))
        ).scalar_one_or_none()
    return child, item


async def save_and_record(
    session: AsyncSession,
    client,
    item_id: int,
    child_id: int | None,
    url: str,
    suggested_name: str,
    source_kind: str,
) -> Attachment | None:
    """Download `url`, dedup by SHA-256, upsert an Attachment row. Returns the row.

    Files are written to `data/rawdata/<kid_slug>/attachments/` with a
    human-readable filename derived from the assignment's date, subject, and
    title — NOT the raw sha256. SHA is kept in the DB for dedup + as the
    collision-guard suffix in the filename.
    """
    try:
        body, ctype = await _fetch_bytes(client, url)
    except Exception as e:
        log.warning("attachment fetch failed: %s (%s)", url[:120], e)
        return None

    sha = hashlib.sha256(body).hexdigest()
    # Check for existing row with same (item_id, sha256).
    existing = (
        await session.execute(
            select(Attachment)
            .where(Attachment.item_id == item_id)
            .where(Attachment.sha256 == sha)
        )
    ).scalar_one_or_none()
    if existing is not None:
        from datetime import datetime, timezone
        existing.last_seen_at = datetime.now(tz=timezone.utc)
        return existing

    child, item = await _load_child_and_item(session, item_id, child_id)
    if child is None:
        # Fall back to legacy sha-bucket layout if we somehow can't resolve
        # the kid. Shouldn't happen in practice; keeps the writer defensive.
        log.warning("attachment save: no child row for item_id=%s; using fallback path", item_id)
        legacy_root = P.data_root() / "attachments" / sha[:2]
        legacy_root.mkdir(parents=True, exist_ok=True)
        ext = _guess_ext(suggested_name, ctype)
        local = legacy_root / (sha + ext)
    else:
        ext = _guess_ext(suggested_name, ctype)
        date_iso = (item.due_or_date if item else None) or (
            item.first_seen_at.date().isoformat() if item and item.first_seen_at else None
        )
        human = P.attachment_filename(
            date_iso=date_iso,
            subject=item.subject if item else None,
            title=item.title if item else suggested_name,
            sha256_hex=sha,
            ext=ext,
        )
        local = P.kid_attachments_dir(child) / human

    if not local.exists():
        local.write_bytes(body)

    att = Attachment(
        item_id=item_id,
        child_id=child_id if child_id is not None else (child.id if child else None),
        filename=suggested_name,
        original_url=url,
        local_path=P.repo_relative(local),
        mime_type=ctype,
        size_bytes=len(body),
        sha256=sha,
        source_kind=source_kind,
    )
    session.add(att)
    try:
        await session.flush()
    except Exception as e:
        # race: someone else inserted; fetch it
        log.warning("attachment flush failed, retrying: %s", e)
        await session.rollback()
        existing = (
            await session.execute(
                select(Attachment)
                .where(Attachment.item_id == item_id)
                .where(Attachment.sha256 == sha)
            )
        ).scalar_one_or_none()
        return existing
    return att


async def extract_and_save(
    session: AsyncSession,
    client,
    item_id: int,
    child_id: int | None,
    detail_html: str,
    source_kind: str,
) -> int:
    """Scan `detail_html`, download every plausible attachment, return count saved."""
    links = extract_attachment_links(detail_html)
    saved = 0
    for link in links:
        att = await save_and_record(
            session, client, item_id=item_id, child_id=child_id,
            url=link["url"], suggested_name=link["filename"],
            source_kind=source_kind,
        )
        if att is not None:
            saved += 1
    return saved
