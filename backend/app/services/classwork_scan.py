"""Classwork-scan upload + Vision extraction.

The parent uploads a photo / PDF / scan of recent classwork (notebook
page, blackboard photo, worksheet). This service:

  1. Saves the file via the existing `attachments` table with
     source_kind='practice_classwork' so dedup + path resolution
     piggy-back on the same plumbing as portal attachments.
  2. Runs Claude Vision over it to extract:
        - the visible text (best-effort OCR)
        - a one-line summary of what the page covers
        - a list of topics seen on the page
     Cached on `practice_classwork_scan` so re-iteration is free.
  3. Optionally binds the scan to a PracticeSession so the practice
     generator picks it up as grounding context.

Storage layout: data/practice_classwork/<child_slug>/<sha-prefix>/<filename>
SHA-256 dedup so re-uploading the same photo silently keeps one row.

Limits: 10 MB / file (phone photos run 4-6 MB), JPG/PNG/HEIC/WEBP/PDF.
"""
from __future__ import annotations

import base64
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
from ..llm.client import LLMClient
from ..models import (
    Attachment, Child, PracticeClassworkScan, PracticeSession,
)


log = logging.getLogger(__name__)

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

# Two purposes share the same scan table + storage layout:
#   classwork_reference  — photo of what was covered in class
#   student_work         — photo of the kid's COMPLETED assignment
PURPOSE_CLASSWORK = "classwork_reference"
PURPOSE_STUDENT_WORK = "student_work"
ALLOWED_PURPOSES = {PURPOSE_CLASSWORK, PURPOSE_STUDENT_WORK}


def _slug(s: str) -> str:
    s = (s or "").strip().lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-") or "unknown"


def _scan_dir(child: Child) -> Path:
    return (
        REPO_ROOT / "data" / "practice_classwork"
        / _slug(child.display_name or f"child{child.id}")
    )


def _mime_for(filename: str, fallback: str | None) -> str:
    ext = Path(filename).suffix.lower()
    return MIME_BY_EXT.get(ext, fallback or "application/octet-stream")


async def save_scan(
    session: AsyncSession,
    child: Child,
    *,
    subject: str,
    filename: str,
    data: bytes,
    session_id: int | None = None,
    extract: bool = True,
    purpose: str = PURPOSE_CLASSWORK,
) -> dict[str, Any]:
    """Persist + (optionally) extract a scan. Returns the full scan
    dict — when `extract=True`, the Vision call runs inline so the
    caller sees `extracted_summary` populated; when False, the row's
    extracted_* fields stay null until called explicitly.

    `purpose` switches the Vision prompt:
      - classwork_reference (default) → "summarise what was covered"
      - student_work → "transcribe what the kid actually wrote"
    """
    if purpose not in ALLOWED_PURPOSES:
        raise ValueError(f"purpose must be one of {sorted(ALLOWED_PURPOSES)}, got {purpose!r}")
    if len(data) > MAX_BYTES:
        raise ValueError(f"file > {MAX_BYTES // (1024 * 1024)} MB cap")
    mime = _mime_for(filename, None)
    if mime not in ALLOWED_MIMES:
        raise ValueError(
            f"unsupported file type {mime!r}; allowed: image/* and PDF"
        )

    sha = hashlib.sha256(data).hexdigest()
    folder = _scan_dir(child) / sha[:2]
    folder.mkdir(parents=True, exist_ok=True)
    safe_name = re.sub(r"[^A-Za-z0-9._-]+", "_", filename) or f"{sha[:8]}{Path(filename).suffix or '.bin'}"
    target = folder / safe_name
    if target.exists():
        existing = target.read_bytes()
        if hashlib.sha256(existing).hexdigest() != sha:
            target = folder / f"{sha[:8]}_{safe_name}"
    target.write_bytes(data)
    rel = target.relative_to(REPO_ROOT)

    # Reuse an existing attachment row if SHA matches (dedup).
    att = (
        await session.execute(
            select(Attachment)
            .where(Attachment.child_id == child.id)
            .where(Attachment.sha256 == sha)
            .where(Attachment.source_kind == "practice_classwork")
        )
    ).scalar_one_or_none()
    if att is None:
        att = Attachment(
            item_id=None,
            child_id=child.id,
            filename=safe_name,
            original_url=f"upload://practice_classwork/{child.id}/{safe_name}",
            local_path=str(rel),
            mime_type=mime,
            size_bytes=len(data),
            sha256=sha,
            kind="image" if mime.startswith("image/") else "pdf",
            source_kind="practice_classwork",
            topic_subject=subject,
        )
        session.add(att)
        await session.flush()

    scan = (
        await session.execute(
            select(PracticeClassworkScan).where(PracticeClassworkScan.attachment_id == att.id)
        )
    ).scalar_one_or_none()
    if scan is None:
        scan = PracticeClassworkScan(
            session_id=session_id,
            child_id=child.id,
            subject=subject,
            attachment_id=att.id,
            purpose=purpose,
        )
        session.add(scan)
    else:
        # Re-bind to a (possibly new) session and update purpose.
        if session_id is not None and scan.session_id != session_id:
            scan.session_id = session_id
        if purpose != scan.purpose:
            scan.purpose = purpose
            # Purpose changed → invalidate the old extraction so the
            # right Vision prompt runs.
            scan.extracted_at = None
            scan.extracted_text = None
            scan.extracted_summary = None
            scan.extracted_topics_json = None

    await session.commit()
    await session.refresh(scan)

    if extract and not scan.extracted_at:
        try:
            await _extract_inline(session, scan, data, mime)
        except Exception as e:
            log.exception("classwork scan vision extraction failed: %s", e)

    return _to_dict(scan)


async def _extract_inline(
    session: AsyncSession,
    scan: PracticeClassworkScan,
    data: bytes,
    mime: str,
) -> None:
    """Synchronous Vision extraction. Pulls Claude Opus over the image,
    asks for {text_excerpt, summary, topics} as strict JSON. Caches
    the result on the scan row. The prompt branches on `scan.purpose`."""
    text, summary, topics = await _run_vision(
        data, mime, subject=scan.subject, purpose=scan.purpose,
    )
    scan.extracted_text = text
    scan.extracted_summary = summary
    scan.extracted_topics_json = json.dumps(topics, ensure_ascii=False) if topics else None
    scan.extracted_at = datetime.now(tz=timezone.utc)
    await session.commit()


VISION_SYSTEM_CLASSWORK = """You are an OCR + topic-extraction assistant. The image is a photo of a school student's recent classwork — a notebook page, blackboard photo, or worksheet that the TEACHER produced or the kid was being taught from.

Output STRICT JSON only:

{
  "text_excerpt": "<verbatim transcript of the visible content, up to 2000 chars>",
  "summary": "<one sentence: what does this page cover?>",
  "topics": ["<short topic phrase>", "..."]   // 1-6 items, lowercase noun phrases
}

RULES:
- Transcribe visible text faithfully. For non-Latin scripts (Devanagari, etc.), preserve the original script.
- The summary is for the parent's eye — natural English, plain noun phrases.
- Topics should match curriculum-style names (e.g. "decimals", "fractions", "verb tenses", "photosynthesis"), not page titles.
- Return ONLY the JSON object. No prose, no fences."""


VISION_SYSTEM_STUDENT_WORK = """You are an OCR assistant. The image is a photo of a school student's COMPLETED ASSIGNMENT — homework the kid has actually done. Your job is to faithfully transcribe what the kid wrote, NOT to grade it or summarise the topic.

Output STRICT JSON only:

{
  "text_excerpt": "<verbatim transcript of what the kid wrote, up to 3000 chars; preserve struck-out text, arrows, scribbles as best you can — note them as [crossed out: ...] or [arrow]>",
  "summary": "<one sentence describing what the kid did on this page (e.g. 'solved 6 fraction-addition problems' / 'wrote a short paragraph about Diwali')>",
  "topics": ["<noun phrase>", "..."]   // 1-6 lowercase topic tags, what subject content this work covers
}

RULES:
- Transcribe FAITHFULLY — keep wrong spellings, arithmetic mistakes, half-erased writing exactly as they appear. Don't correct anything.
- For non-Latin scripts (Devanagari, etc.), preserve the original script.
- The summary names what the kid DID, not what they should have done.
- Return ONLY the JSON object. No prose, no fences."""


async def _run_vision(
    data: bytes, mime: str, *, subject: str, purpose: str = PURPOSE_CLASSWORK,
) -> tuple[str | None, str | None, list[str] | None]:
    """Best-effort Vision call. Falls back to (None, None, None) when
    the LLM is unreachable or returns invalid output — the practice
    generator simply won't have scan grounding for this iteration.

    Image MIMEs go through Claude Vision (base64 in the prompt). PDFs
    are not OCR'd here; we record the file but leave extraction empty
    so the LLM at least sees "a PDF was uploaded for this subject."
    """
    if mime == "application/pdf":
        return (None, "PDF uploaded — extraction not supported by Vision pipeline yet.", None)

    client = LLMClient()
    if not client.enabled():
        return (None, None, None)

    is_student_work = (purpose == PURPOSE_STUDENT_WORK)
    system_prompt = VISION_SYSTEM_STUDENT_WORK if is_student_work else VISION_SYSTEM_CLASSWORK
    label = "student_work" if is_student_work else "classwork"
    log_purpose = (
        "practice_student_vision" if is_student_work else "practice_classwork_vision"
    )

    b64 = base64.b64encode(data).decode("ascii")
    prompt_parts = [
        f"Subject: {subject}",
        "",
        f"![{label}](data:{mime};base64,{b64[:200000]})",
        "",
        "Extract the JSON described in the system prompt.",
    ]
    try:
        resp = await client.complete(
            purpose=log_purpose,
            system=system_prompt,
            prompt="\n".join(prompt_parts),
            max_tokens=1500,
        )
    except Exception as e:
        log.warning("classwork vision: LLM call failed: %s", e)
        return (None, None, None)
    text = (resp.text or "").strip()
    if text.startswith("```"):
        parts = text.split("```", 2)
        if len(parts) >= 2:
            text = parts[1]
            if text.lstrip().startswith("json"):
                text = text.split("\n", 1)[1] if "\n" in text else text
    try:
        out = json.loads(text)
    except Exception:
        log.warning("classwork vision: bad JSON; raw=%r", text[:200])
        return (None, None, None)
    excerpt = out.get("text_excerpt") if isinstance(out.get("text_excerpt"), str) else None
    summary = out.get("summary") if isinstance(out.get("summary"), str) else None
    topics = out.get("topics") if isinstance(out.get("topics"), list) else None
    if topics is not None:
        topics = [str(t).strip() for t in topics if isinstance(t, str) and t.strip()][:6]
    return excerpt, summary, topics


async def list_scans(
    session: AsyncSession,
    *,
    child_id: int | None = None,
    subject: str | None = None,
    session_id: int | None = None,
    purpose: str | None = None,
    unbound_only: bool = False,
    limit: int = 100,
) -> list[dict[str, Any]]:
    q = select(PracticeClassworkScan).order_by(PracticeClassworkScan.uploaded_at.desc())
    if child_id is not None:
        q = q.where(PracticeClassworkScan.child_id == child_id)
    if subject:
        q = q.where(PracticeClassworkScan.subject == subject)
    if session_id is not None:
        q = q.where(PracticeClassworkScan.session_id == session_id)
    elif unbound_only:
        q = q.where(PracticeClassworkScan.session_id.is_(None))
    if purpose:
        q = q.where(PracticeClassworkScan.purpose == purpose)
    q = q.limit(limit)
    rows = (await session.execute(q)).scalars().all()
    return [_to_dict(r) for r in rows]


async def bind_scan(
    session: AsyncSession,
    scan_id: int,
    practice_session_id: int | None,
) -> dict[str, Any]:
    """Move a scan in/out of a practice session. Pass session_id=None
    to detach (becomes a free-floating scan)."""
    scan = (
        await session.execute(
            select(PracticeClassworkScan).where(PracticeClassworkScan.id == scan_id)
        )
    ).scalar_one_or_none()
    if scan is None:
        raise ValueError(f"scan {scan_id} not found")
    if practice_session_id is not None:
        sess = (
            await session.execute(
                select(PracticeSession).where(PracticeSession.id == practice_session_id)
            )
        ).scalar_one_or_none()
        if sess is None:
            raise ValueError(f"practice session {practice_session_id} not found")
    scan.session_id = practice_session_id
    await session.commit()
    await session.refresh(scan)
    return _to_dict(scan)


async def delete_scan(session: AsyncSession, scan_id: int) -> bool:
    """Delete a scan. The underlying attachment row is deleted by
    cascade. The on-disk file is left in place for now (cleanup can
    be a separate retention pass)."""
    scan = (
        await session.execute(
            select(PracticeClassworkScan).where(PracticeClassworkScan.id == scan_id)
        )
    ).scalar_one_or_none()
    if scan is None:
        return False
    # Manually clear the attachment too; we set ondelete=CASCADE on the
    # FK but SQLite doesn't always honor it through the ORM layer.
    att = (
        await session.execute(
            select(Attachment).where(Attachment.id == scan.attachment_id)
        )
    ).scalar_one_or_none()
    await session.delete(scan)
    if att is not None:
        await session.delete(att)
    await session.commit()
    return True


def _to_dict(scan: PracticeClassworkScan) -> dict[str, Any]:
    topics: Any = None
    if scan.extracted_topics_json:
        try:
            topics = json.loads(scan.extracted_topics_json)
        except Exception:
            topics = None
    return {
        "id": scan.id,
        "session_id": scan.session_id,
        "child_id": scan.child_id,
        "subject": scan.subject,
        "attachment_id": scan.attachment_id,
        "purpose": scan.purpose,
        "extracted_summary": scan.extracted_summary,
        "extracted_topics": topics,
        "extracted_text_present": bool(scan.extracted_text),
        "extracted_at": scan.extracted_at.isoformat() if scan.extracted_at else None,
        "uploaded_at": scan.uploaded_at.isoformat() if scan.uploaded_at else None,
    }
