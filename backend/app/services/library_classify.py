"""LLM-driven classification of library uploads.

For each new file we hand Claude:
  - filename + mime + size
  - up to 3000 chars of extracted text (PDFs via pypdf, plain-text
    direct, DOCX via python-docx-2txt; falls back to filename-only
    for image / unrecognised binaries)

Claude returns strict JSON:
  {
    "kind":        textbook | workbook | reference | study_guide |
                   newsletter | syllabus | test_paper | scanned_notes |
                   project | other,
    "subject":     "English" | "Hindi" | "Mathematics" | … | null,
    "class_level": 4 | 6 | … | null,
    "summary":     "<2-3 sentence description, ≤ 60 words>",
    "keywords":    ["…"]                        (≤ 8 short tokens)
  }

The validator rejects (and stores a llm_error instead) if `kind` isn't
in the allowed set or the JSON is malformed. Better to leave the row
unclassified than to lie.
"""
from __future__ import annotations

import io
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import REPO_ROOT
from ..llm.client import LLMClient
from ..models import LibraryFile


log = logging.getLogger(__name__)


VALID_KINDS = {
    "textbook", "workbook", "reference", "study_guide",
    "newsletter", "syllabus", "test_paper", "scanned_notes",
    "project", "other",
}

EXTRACT_CHARS = 3000


SYSTEM_PROMPT = """You classify school-related files for a parent-cockpit library.

You'll receive metadata (filename, mime, size) and the first ~3000
chars of extracted text. Return STRICT JSON:

{
  "kind": "<one of: textbook | workbook | reference | study_guide | newsletter | syllabus | test_paper | scanned_notes | project | other>",
  "subject": "<English | Hindi | Sanskrit | Mathematics | Science | Social Science | Computer Science | Art | Music | … | null>",
  "class_level": <int 1-12 | null>,
  "summary": "<2-3 sentence factual description, ≤ 60 words. State what the file IS, not what it 'might be'.>",
  "keywords": [ "<short token>", ... ]    // 0-8 items
}

Rules:
- Output ONLY the JSON object, no prose, no fences.
- `subject` is null when the file isn't subject-specific (e.g. a generic newsletter).
- `class_level` is null when not inferable.
- Don't invent a class level from "Class 4" appearing once if the rest
  of the document is generic. Prefer null over guessing.
- `summary` describes content, not utility ("don't tell the parent how
  to use it" — just say what it is).
- `kind=other` is a valid last resort. Do not stretch.
"""


def _extract_pdf_text(path: Path, max_chars: int = EXTRACT_CHARS) -> str | None:
    try:
        from pypdf import PdfReader
    except Exception as e:
        log.warning("pypdf unavailable: %s", e)
        return None
    try:
        reader = PdfReader(str(path))
    except Exception as e:
        log.warning("PDF read failed for %s: %s", path, e)
        return None
    out: list[str] = []
    total = 0
    for page in reader.pages[:20]:  # cap pages
        try:
            t = page.extract_text() or ""
        except Exception:
            continue
        out.append(t)
        total += len(t)
        if total >= max_chars:
            break
    text = "\n".join(out).strip()
    if not text:
        return None
    return text[:max_chars]


def _extract_text(path: Path, max_chars: int = EXTRACT_CHARS) -> str | None:
    try:
        return path.read_text(encoding="utf-8", errors="replace")[:max_chars]
    except Exception as e:
        log.warning("text read failed for %s: %s", path, e)
        return None


def _extract_docx_text(path: Path, max_chars: int = EXTRACT_CHARS) -> str | None:
    try:
        from docx import Document  # type: ignore
    except Exception:
        log.info("python-docx not installed; skipping docx text extract")
        return None
    try:
        doc = Document(str(path))
        text = "\n".join(p.text for p in doc.paragraphs if p.text)
        return text[:max_chars] or None
    except Exception as e:
        log.warning("docx extract failed for %s: %s", path, e)
        return None


def _extract_epub_text(path: Path, max_chars: int = EXTRACT_CHARS) -> str | None:
    """EPUB is a ZIP of XHTML chapters + an OPF manifest. Stdlib only —
    no `ebooklib` dep. Reads the spine in document order, strips tags,
    returns the first ~3000 chars (which on a textbook is usually
    title page + intro / TOC + first chapter — enough for classify)."""
    try:
        import re as _re
        import zipfile
        from xml.etree import ElementTree as ET
    except Exception:
        return None
    try:
        with zipfile.ZipFile(path, "r") as z:
            # Find content.opf via container.xml.
            opf_path: str | None = None
            try:
                container = z.read("META-INF/container.xml").decode("utf-8", "replace")
                m = _re.search(r'full-path="([^"]+\.opf)"', container)
                if m:
                    opf_path = m.group(1)
            except Exception:
                pass
            # Fallback: search for the .opf file directly.
            if not opf_path:
                for n in z.namelist():
                    if n.lower().endswith(".opf"):
                        opf_path = n
                        break
            if not opf_path:
                return None
            opf_xml = z.read(opf_path).decode("utf-8", "replace")
            # Parse the spine — list of itemrefs in reading order.
            try:
                root = ET.fromstring(opf_xml)
            except ET.ParseError:
                return None
            ns = {
                "opf": "http://www.idpf.org/2007/opf",
            }
            manifest: dict[str, str] = {}
            for item in root.findall(".//opf:manifest/opf:item", ns):
                manifest[item.attrib.get("id", "")] = item.attrib.get("href", "")
            spine_ids = [
                ir.attrib.get("idref", "")
                for ir in root.findall(".//opf:spine/opf:itemref", ns)
            ]
            opf_dir = "/".join(opf_path.split("/")[:-1])
            text_chunks: list[str] = []
            total = 0
            for sid in spine_ids[:6]:  # cap at first 6 spine items
                href = manifest.get(sid)
                if not href:
                    continue
                full = f"{opf_dir}/{href}" if opf_dir else href
                try:
                    raw = z.read(full).decode("utf-8", "replace")
                except KeyError:
                    continue
                # Strip tags + collapse whitespace.
                stripped = _re.sub(r"<[^>]+>", " ", raw)
                stripped = _re.sub(r"\s+", " ", stripped).strip()
                if not stripped:
                    continue
                text_chunks.append(stripped)
                total += len(stripped)
                if total >= max_chars:
                    break
            text = " ".join(text_chunks).strip()
            return text[:max_chars] if text else None
    except Exception as e:
        log.warning("epub extract failed for %s: %s", path, e)
        return None


def extract_text_for(path: Path, mime_type: str | None) -> str | None:
    """Best-effort text extraction by mime. Returns None for binaries
    (images / Excel) — caller still classifies based on filename + size."""
    if mime_type == "application/pdf":
        return _extract_pdf_text(path)
    if mime_type == "application/epub+zip" or path.suffix.lower() == ".epub":
        return _extract_epub_text(path)
    if mime_type and (mime_type.startswith("text/") or "csv" in mime_type):
        return _extract_text(path)
    if mime_type and "wordprocessingml" in mime_type:
        return _extract_docx_text(path)
    return None


def _build_prompt(row: LibraryFile, text: str | None) -> str:
    parts = [
        f"filename: {row.original_filename or row.filename}",
        f"mime: {row.mime_type or 'unknown'}",
        f"size_bytes: {row.size_bytes or 0}",
    ]
    if row.note:
        parts.append(f"note: {row.note}")
    if text:
        parts.append("---")
        parts.append("EXTRACTED TEXT (first ~3000 chars):")
        parts.append(text)
    else:
        parts.append("---")
        parts.append("(no text could be extracted; classify by filename + size + mime)")
    return "\n".join(parts)


def _validate_classification(out: dict[str, Any]) -> str | None:
    kind = out.get("kind")
    if not isinstance(kind, str) or kind not in VALID_KINDS:
        return f"kind must be one of {sorted(VALID_KINDS)}, got {kind!r}"
    if "subject" not in out:
        return "subject missing (use null if not applicable)"
    if "class_level" not in out:
        return "class_level missing (use null if not inferable)"
    cl = out.get("class_level")
    if cl is not None and not (isinstance(cl, int) and 1 <= cl <= 12):
        return f"class_level must be int 1-12 or null, got {cl!r}"
    if not isinstance(out.get("summary", ""), str) or not out["summary"].strip():
        return "summary missing"
    kw = out.get("keywords", [])
    if not isinstance(kw, list):
        return "keywords must be a list"
    return None


async def classify_one(
    session: AsyncSession, library_id: int,
) -> dict[str, Any]:
    """Classify one library row in-place. Updates llm_* columns and
    returns the parsed classification dict (or {error: ...})."""
    row = (
        await session.execute(
            select(LibraryFile).where(LibraryFile.id == library_id)
        )
    ).scalar_one_or_none()
    if row is None:
        return {"error": f"library row {library_id} not found"}

    path = (REPO_ROOT / row.local_path).resolve()
    if not path.exists():
        row.llm_error = "file vanished on disk"
        row.llm_processed_at = datetime.now(tz=timezone.utc)
        await session.commit()
        return {"error": "file vanished on disk"}

    text = extract_text_for(path, row.mime_type)

    client = LLMClient()
    if not client.enabled():
        row.llm_error = "LLM disabled"
        row.llm_processed_at = datetime.now(tz=timezone.utc)
        await session.commit()
        return {"error": "LLM disabled"}

    prompt = _build_prompt(row, text)
    try:
        resp = await client.complete(
            purpose="library_classify",
            system=SYSTEM_PROMPT,
            prompt=prompt,
            max_tokens=512,
        )
    except Exception as e:
        log.warning("library classify LLM call failed (id=%s): %s", library_id, e)
        row.llm_error = repr(e)[:300]
        row.llm_processed_at = datetime.now(tz=timezone.utc)
        await session.commit()
        return {"error": str(e)}

    raw = (resp.text or "").strip()
    if raw.startswith("```"):
        # strip fenced code if the model added one
        raw = raw.split("```", 2)
        raw = raw[1] if len(raw) >= 2 else "".join(raw)
        if raw.lstrip().startswith("json"):
            raw = raw.split("\n", 1)[1] if "\n" in raw else raw
    try:
        parsed = json.loads(raw)
    except Exception as e:
        log.warning("library classify JSON parse failed (id=%s): %s", library_id, e)
        row.llm_error = f"non-JSON output: {raw[:200]}"
        row.llm_processed_at = datetime.now(tz=timezone.utc)
        await session.commit()
        return {"error": "non-JSON LLM output"}

    err = _validate_classification(parsed)
    if err:
        row.llm_error = f"validation: {err}"
        row.llm_processed_at = datetime.now(tz=timezone.utc)
        await session.commit()
        return {"error": err}

    row.llm_kind = parsed["kind"]
    row.llm_subject = parsed.get("subject")
    row.llm_class_level = parsed.get("class_level")
    row.llm_summary = parsed["summary"].strip()
    row.llm_keywords = json.dumps(parsed.get("keywords") or [])
    row.llm_model = resp.model
    row.llm_processed_at = datetime.now(tz=timezone.utc)
    row.llm_error = None
    await session.commit()
    return parsed


async def reclassify_all(
    session: AsyncSession, *, force: bool = False, limit: int | None = None,
) -> dict[str, int]:
    """Re-run classification on every (or every-unprocessed) row."""
    q = select(LibraryFile)
    if not force:
        q = q.where(LibraryFile.llm_processed_at.is_(None))
    if limit is not None:
        q = q.limit(limit)
    rows = (await session.execute(q)).scalars().all()
    classified = failed = 0
    for r in rows:
        out = await classify_one(session, r.id)
        if out.get("error"):
            failed += 1
        else:
            classified += 1
    return {"scanned": len(rows), "classified": classified, "failed": failed}
