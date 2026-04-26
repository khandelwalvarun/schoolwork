"""Portfolio storage — per-(subject, topic) attachments for a kid.

Phase 20 lets the parent attach a photo / scan / drawing to a syllabus
topic so the kid's record gains a portfolio dimension beyond the
school's gradebook. Storage lives under
`data/portfolio/<kid-slug>/<subject-slug>/<topic-slug>/<filename>`
on disk, with a row in the existing `attachments` table tagged
source_kind='portfolio_upload' and bound to (child_id, topic_subject,
topic_topic).

Design notes:
  - Bind by natural key (subject + topic strings), NOT FK to topic_state.
    That table gets wiped + rebuilt nightly; an FK there would break.
  - SHA-256 used as a dedup key — re-uploading the same image silently
    keeps one row, which matches the existing pipeline's invariant.
  - File-size cap (10 MB) per upload — phone photos are typically 4-6 MB.
"""
from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import REPO_ROOT
from ..models import Attachment, Child


MAX_BYTES = 10 * 1024 * 1024  # 10 MB
ALLOWED_MIMES = {
    "image/jpeg", "image/png", "image/webp", "image/heic", "image/heif",
    "application/pdf",
}
MIME_BY_EXT = {
    ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
    ".png": "image/png", ".webp": "image/webp",
    ".heic": "image/heic", ".heif": "image/heif",
    ".pdf": "application/pdf",
}


def _slug(s: str) -> str:
    s = s.strip().lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    s = s.strip("-")
    return s or "unknown"


def _portfolio_dir(child: Child, subject: str, topic: str) -> Path:
    base = REPO_ROOT / "data" / "portfolio"
    return base / _slug(child.display_name or f"child{child.id}") / _slug(subject) / _slug(topic)


def _ext_of(filename: str) -> str:
    p = Path(filename)
    return p.suffix.lower()


def _mime_for(filename: str, fallback: str | None) -> str:
    return MIME_BY_EXT.get(_ext_of(filename), fallback or "application/octet-stream")


async def save_portfolio_upload(
    session: AsyncSession,
    child: Child,
    subject: str,
    topic: str,
    filename: str,
    data: bytes,
    note: str | None = None,
) -> Attachment:
    if not subject or not topic:
        raise ValueError("subject and topic are required")
    if len(data) > MAX_BYTES:
        raise ValueError(f"file > {MAX_BYTES // (1024 * 1024)} MB cap")
    mime = _mime_for(filename, None)
    if mime not in ALLOWED_MIMES:
        raise ValueError(
            f"unsupported file type {mime!r}; allowed: image/* and PDF"
        )

    sha = hashlib.sha256(data).hexdigest()
    # Dedup against existing portfolio row for same kid/topic/sha.
    existing = (
        await session.execute(
            select(Attachment)
            .where(Attachment.child_id == child.id)
            .where(Attachment.topic_subject == subject)
            .where(Attachment.topic_topic == topic)
            .where(Attachment.sha256 == sha)
        )
    ).scalar_one_or_none()
    if existing is not None:
        existing.last_seen_at = datetime.now(tz=timezone.utc)
        return existing

    folder = _portfolio_dir(child, subject, topic)
    folder.mkdir(parents=True, exist_ok=True)
    safe_name = re.sub(r"[^A-Za-z0-9._-]+", "_", filename) or f"{sha[:8]}{_ext_of(filename) or '.bin'}"
    target = folder / safe_name
    # If a file with the same name exists with different content, prefix the sha.
    if target.exists():
        existing_bytes = target.read_bytes()
        if hashlib.sha256(existing_bytes).hexdigest() != sha:
            target = folder / f"{sha[:8]}_{safe_name}"
    target.write_bytes(data)

    rel = target.relative_to(REPO_ROOT)
    row = Attachment(
        item_id=None,
        child_id=child.id,
        filename=safe_name,
        original_url=f"upload://{child.id}/{subject}/{topic}/{safe_name}",
        local_path=str(rel),
        mime_type=mime,
        size_bytes=len(data),
        sha256=sha,
        kind="image" if mime.startswith("image/") else "pdf",
        source_kind="portfolio_upload",
        note=note,
        topic_subject=subject,
        topic_topic=topic,
    )
    session.add(row)
    await session.flush()
    await session.refresh(row)
    return row


async def list_portfolio(
    session: AsyncSession,
    *,
    child_id: int | None = None,
    subject: str | None = None,
    topic: str | None = None,
) -> list[dict[str, Any]]:
    q = (
        select(Attachment)
        .where(Attachment.source_kind == "portfolio_upload")
        .order_by(Attachment.downloaded_at.desc())
    )
    if child_id is not None:
        q = q.where(Attachment.child_id == child_id)
    if subject is not None:
        q = q.where(Attachment.topic_subject == subject)
    if topic is not None:
        q = q.where(Attachment.topic_topic == topic)
    rows = (await session.execute(q)).scalars().all()
    return [
        {
            "id": r.id,
            "child_id": r.child_id,
            "subject": r.topic_subject,
            "topic": r.topic_topic,
            "filename": r.filename,
            "mime_type": r.mime_type,
            "size_bytes": r.size_bytes,
            "kind": r.kind,
            "note": r.note,
            "uploaded_at": r.downloaded_at.isoformat() if r.downloaded_at else None,
            "sha256": r.sha256,
        }
        for r in rows
    ]


async def delete_portfolio(
    session: AsyncSession, attachment_id: int,
) -> bool:
    row = (
        await session.execute(
            select(Attachment).where(Attachment.id == attachment_id)
        )
    ).scalar_one_or_none()
    if row is None or row.source_kind != "portfolio_upload":
        return False
    # Remove the file off-disk if it lives under data/portfolio/.
    try:
        path = (REPO_ROOT / row.local_path).resolve()
        portfolio_root = (REPO_ROOT / "data" / "portfolio").resolve()
        if str(path).startswith(str(portfolio_root)):
            if path.exists():
                path.unlink()
    except Exception:
        # Best-effort — DB row removal is the source of truth.
        pass
    await session.delete(row)
    return True
