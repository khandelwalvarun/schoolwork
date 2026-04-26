"""Library — parent-uploaded files (textbooks, study material, etc.).

The companion to services/portfolio.py: portfolio is small per-topic
images / scans; library is freeform reference material the parent
wants the cockpit to know about. After upload, an LLM classifier
fills in `llm_*` fields (kind, subject, class_level, summary,
keywords) so the file can be filtered + searched alongside scraped
data.

Storage: data/library/<sha-prefix-2>/<safe-filename>
SHA-256 dedup on the column means re-uploading the same file silently
reuses the existing row (we update last-seen but not classification).

Allowed types: PDF, plain text, markdown, HEIC/PNG/JPG, DOCX. Anything
the LLM can usefully describe; binary blobs without text get
"unsupported" classification but stay visible.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import REPO_ROOT
from ..models import Child, LibraryFile


log = logging.getLogger(__name__)

MAX_BYTES = 50 * 1024 * 1024   # 50 MB — textbook PDFs can run large
ALLOWED_MIMES = {
    "application/pdf",
    "application/epub+zip",   # .epub e-books
    "text/plain", "text/markdown", "text/csv",
    "image/jpeg", "image/png", "image/webp", "image/heic", "image/heif",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",  # .docx
    "application/msword",
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",  # .xlsx
    "application/zip",        # some browsers report epub as zip — fall through
}
MIME_BY_EXT = {
    ".pdf": "application/pdf",
    ".epub": "application/epub+zip",
    ".txt": "text/plain",
    ".md":  "text/markdown",
    ".csv": "text/csv",
    ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
    ".png": "image/png", ".webp": "image/webp",
    ".heic": "image/heic", ".heif": "image/heif",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".doc": "application/msword",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".xls": "application/vnd.ms-excel",
}


def _slug(s: str) -> str:
    s = (s or "").strip()
    # Keep dot for extension; collapse other punctuation.
    s = re.sub(r"[^A-Za-z0-9._-]+", "_", s)
    return s.strip("._-") or "unnamed"


def _mime_for(filename: str, fallback: str | None) -> str:
    ext = Path(filename).suffix.lower()
    return MIME_BY_EXT.get(ext, fallback or "application/octet-stream")


def _local_path_for(sha: str, filename: str) -> Path:
    """Bucket files into 256 prefix-folders so the directory doesn't
    accumulate 10k flat entries."""
    base = REPO_ROOT / "data" / "library" / sha[:2]
    return base / filename


async def save_library_upload(
    session: AsyncSession,
    *,
    filename: str,
    data: bytes,
    child_id: int | None = None,
    note: str | None = None,
    classify: bool = True,
) -> LibraryFile:
    """Persist a freshly-uploaded file. Idempotent on SHA-256 — the
    same content uploaded twice keeps one row.

    If `classify=True` (default), the LLM classifier kicks off
    asynchronously so the upload returns fast; classification fills
    in `llm_*` columns when it lands."""
    if len(data) > MAX_BYTES:
        raise ValueError(f"file > {MAX_BYTES // (1024 * 1024)} MB cap")
    mime = _mime_for(filename, None)
    if mime not in ALLOWED_MIMES:
        raise ValueError(
            f"unsupported file type {mime!r}; allowed: PDF, text, image, docx, xlsx"
        )

    sha = hashlib.sha256(data).hexdigest()
    existing = (
        await session.execute(
            select(LibraryFile).where(LibraryFile.sha256 == sha)
        )
    ).scalar_one_or_none()
    if existing is not None:
        # Update child_id / note if the new upload provided them.
        changed = False
        if child_id is not None and existing.child_id != child_id:
            existing.child_id = child_id
            changed = True
        if note and not existing.note:
            existing.note = note
            changed = True
        if changed:
            await session.commit()
            await session.refresh(existing)
        return existing

    safe_name = _slug(filename)
    target = _local_path_for(sha, safe_name)
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        # Same name, different sha (caught above) shouldn't happen — but if
        # somehow it does, prefix with sha to disambiguate.
        target = target.parent / f"{sha[:8]}_{safe_name}"
    target.write_bytes(data)

    rel = target.relative_to(REPO_ROOT)
    row = LibraryFile(
        filename=safe_name,
        original_filename=filename,
        sha256=sha,
        size_bytes=len(data),
        mime_type=mime,
        local_path=str(rel),
        child_id=child_id,
        note=note,
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)

    if classify:
        # Fire-and-forget classification. The row is already saved; the
        # background task fills in llm_* columns in a fresh session so
        # the API call returns immediately.
        asyncio.create_task(classify_in_background(row.id))

    return row


async def classify_in_background(library_id: int) -> None:
    """Wraps services.library_classify.classify_one in its own session so
    the upload caller doesn't have to wait for the LLM round-trip."""
    from ..db import get_async_session
    from .library_classify import classify_one
    try:
        async with get_async_session() as session:
            await classify_one(session, library_id)
    except Exception:
        log.exception("library classify-in-background failed (id=%s)", library_id)


async def list_library(
    session: AsyncSession,
    *,
    child_id: int | None = None,
    kind: str | None = None,
    subject: str | None = None,
) -> list[dict[str, Any]]:
    q = select(LibraryFile).order_by(LibraryFile.uploaded_at.desc())
    if child_id is not None:
        q = q.where(LibraryFile.child_id == child_id)
    if kind:
        q = q.where(LibraryFile.llm_kind == kind)
    if subject:
        q = q.where(LibraryFile.llm_subject == subject)
    rows = (await session.execute(q)).scalars().all()
    return [_row_to_dict(r) for r in rows]


async def get_library_row(
    session: AsyncSession, library_id: int,
) -> LibraryFile | None:
    return (
        await session.execute(
            select(LibraryFile).where(LibraryFile.id == library_id)
        )
    ).scalar_one_or_none()


async def delete_library(
    session: AsyncSession, library_id: int,
) -> bool:
    row = await get_library_row(session, library_id)
    if row is None:
        return False
    try:
        path = (REPO_ROOT / row.local_path).resolve()
        library_root = (REPO_ROOT / "data" / "library").resolve()
        if str(path).startswith(str(library_root)) and path.exists():
            path.unlink()
    except Exception:
        # File-system mishap shouldn't block the row delete.
        pass
    await session.delete(row)
    await session.commit()
    return True


def _row_to_dict(r: LibraryFile) -> dict[str, Any]:
    keywords: list[str] = []
    if r.llm_keywords:
        try:
            kw = json.loads(r.llm_keywords)
            if isinstance(kw, list):
                keywords = [str(x) for x in kw]
        except Exception:
            pass
    return {
        "id": r.id,
        "filename": r.filename,
        "original_filename": r.original_filename,
        "sha256": r.sha256,
        "size_bytes": r.size_bytes,
        "mime_type": r.mime_type,
        "child_id": r.child_id,
        "uploaded_at": r.uploaded_at.isoformat() if r.uploaded_at else None,
        "note": r.note,
        "llm_kind": r.llm_kind,
        "llm_subject": r.llm_subject,
        "llm_class_level": r.llm_class_level,
        "llm_summary": r.llm_summary,
        "llm_keywords": keywords,
        "llm_processed_at": (
            r.llm_processed_at.isoformat() if r.llm_processed_at else None
        ),
        "llm_model": r.llm_model,
        "llm_error": r.llm_error,
    }
