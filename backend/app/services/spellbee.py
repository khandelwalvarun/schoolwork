"""Spelling-Bee list index.

Lists live as files in `data/spellbee/`. The user drops PDFs / images /
text files in there — we index them by filename and surface an ordinal
(list number) parsed from the name so the UI can sort + detect matches.

Filename convention (loose; parser is tolerant):
    list-01.pdf, list02.jpg, List 3.txt, spellbee-list-04.pdf, ...

Any file whose name contains a number is picked up; files without a
number sort last. No DB — just filesystem scan.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from ..config import get_settings  # noqa: F401 (kept for future; currently unused)


REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
SPELLBEE_DIR = REPO_ROOT / "data" / "spellbee"

ALLOWED_EXT = {".pdf", ".txt", ".md", ".docx", ".jpg", ".jpeg", ".png", ".gif", ".webp"}

_NUM_RE = re.compile(r"(\d{1,3})")


@dataclass(frozen=True)
class SpellBeeList:
    filename: str
    number: int | None
    size_bytes: int
    mime_type: str

    def to_dict(self) -> dict:
        return {
            "filename": self.filename,
            "number": self.number,
            "size_bytes": self.size_bytes,
            "mime_type": self.mime_type,
            "download_url": f"/api/spellbee/list/{self.filename}",
        }


_MIME_BY_EXT = {
    ".pdf": "application/pdf",
    ".txt": "text/plain",
    ".md": "text/markdown",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".gif": "image/gif",
    ".webp": "image/webp",
}


def _parse_number(stem: str) -> int | None:
    m = _NUM_RE.search(stem)
    if not m:
        return None
    try:
        n = int(m.group(1))
    except ValueError:
        return None
    return n if 0 < n < 1000 else None


def list_lists() -> list[SpellBeeList]:
    SPELLBEE_DIR.mkdir(parents=True, exist_ok=True)
    out: list[SpellBeeList] = []
    for p in SPELLBEE_DIR.iterdir():
        if not p.is_file():
            continue
        ext = p.suffix.lower()
        if ext not in ALLOWED_EXT:
            continue
        out.append(
            SpellBeeList(
                filename=p.name,
                number=_parse_number(p.stem),
                size_bytes=p.stat().st_size,
                mime_type=_MIME_BY_EXT.get(ext, "application/octet-stream"),
            )
        )
    out.sort(key=lambda x: (x.number is None, x.number or 0, x.filename.lower()))
    return out


def resolve_file(filename: str) -> Path | None:
    """Return an absolute path under SPELLBEE_DIR for `filename`, or None.
    Rejects any path that escapes the directory (traversal guard)."""
    if not filename or "/" in filename or "\\" in filename or filename.startswith("."):
        return None
    candidate = (SPELLBEE_DIR / filename).resolve()
    try:
        candidate.relative_to(SPELLBEE_DIR.resolve())
    except ValueError:
        return None
    if not candidate.exists() or not candidate.is_file():
        return None
    if candidate.suffix.lower() not in ALLOWED_EXT:
        return None
    return candidate


_LIST_REF_RE = re.compile(r"\blist\s*[-#]?\s*(\d{1,3})\b", re.IGNORECASE)


def detect_list_reference(*texts: str | None) -> int | None:
    """Scan free text (title, notes, body) for 'List N' / 'list-N' and
    return N if the surrounding context looks spelling-bee related.
    The caller should already know the item is a spelling-bee item; we
    just extract the number."""
    for t in texts:
        if not t:
            continue
        m = _LIST_REF_RE.search(t)
        if m:
            try:
                return int(m.group(1))
            except ValueError:
                continue
    return None


def is_spellbee_text(*texts: str | None) -> bool:
    for t in texts:
        if t and re.search(r"spell(?:ing)?\s*bee", t, re.IGNORECASE):
            return True
    return False
