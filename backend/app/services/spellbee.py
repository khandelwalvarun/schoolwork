"""Spelling-Bee list index (per-kid).

Lists live as files in `data/rawdata/<kid_slug>/spellbee/`. The user drops
PDFs / images / text files in there — we index them by filename and surface
an ordinal (list number) parsed from the name so the UI can sort + detect
matches.

Filename convention (loose; parser is tolerant):
    list-01.pdf, list02.jpg, List 3.txt, spellbee-list-04.pdf, ...

Any file whose name contains a number is picked up; files without a number
sort last. No DB — just filesystem scan.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from ..util import paths as P

if TYPE_CHECKING:
    from ..models import Child


ALLOWED_EXT = {".pdf", ".txt", ".md", ".docx", ".jpg", ".jpeg", ".png", ".gif", ".webp"}

_NUM_RE = re.compile(r"(\d{1,3})")

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


@dataclass(frozen=True)
class SpellBeeList:
    filename: str
    number: int | None
    size_bytes: int
    mime_type: str
    child_id: int
    kid_slug: str

    def to_dict(self) -> dict:
        return {
            "filename": self.filename,
            "number": self.number,
            "size_bytes": self.size_bytes,
            "mime_type": self.mime_type,
            "child_id": self.child_id,
            "kid_slug": self.kid_slug,
            "download_url": f"/api/spellbee/list/{self.child_id}/{self.filename}",
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


def _dir_for(child: "Child") -> Path:
    return P.kid_spellbee_dir(child)


def _row(child: "Child", path: Path) -> SpellBeeList:
    ext = path.suffix.lower()
    return SpellBeeList(
        filename=path.name,
        number=_parse_number(path.stem),
        size_bytes=path.stat().st_size,
        mime_type=_MIME_BY_EXT.get(ext, "application/octet-stream"),
        child_id=child.id,
        kid_slug=P.kid_slug(child),
    )


def list_lists(child: "Child") -> list[SpellBeeList]:
    d = _dir_for(child)
    out: list[SpellBeeList] = []
    for p in d.iterdir():
        if not p.is_file():
            continue
        if p.suffix.lower() not in ALLOWED_EXT:
            continue
        out.append(_row(child, p))
    out.sort(key=lambda x: (x.number is None, x.number or 0, x.filename.lower()))
    return out


_UNSAFE_NAME = re.compile(r"[^A-Za-z0-9._\- ]")


def _sanitize_filename(raw: str) -> str | None:
    name = raw.strip().replace("/", "_").replace("\\", "_")
    if not name or name.startswith("."):
        return None
    p = Path(name)
    stem = _UNSAFE_NAME.sub("_", p.stem).strip() or "file"
    ext = p.suffix.lower()
    if ext not in ALLOWED_EXT:
        return None
    return f"{stem}{ext}"


def save_upload(child: "Child", original_name: str, data: bytes) -> SpellBeeList:
    safe = _sanitize_filename(original_name)
    if safe is None:
        raise ValueError(f"unsupported filename or extension: {original_name!r}")
    target = _dir_for(child) / safe
    target.write_bytes(data)
    return _row(child, target)


def delete_file(child: "Child", filename: str) -> bool:
    path = resolve_file(child, filename)
    if path is None:
        return False
    path.unlink()
    return True


def rename_file(child: "Child", old: str, new: str) -> SpellBeeList:
    src = resolve_file(child, old)
    if src is None:
        raise ValueError(f"spellbee list {old!r} not found")
    safe = _sanitize_filename(new)
    if safe is None:
        raise ValueError(f"unsupported new filename: {new!r}")
    dst = _dir_for(child) / safe
    if dst.exists() and dst.resolve() != src.resolve():
        raise ValueError(f"target {safe!r} already exists")
    src.rename(dst)
    return _row(child, dst)


def resolve_file(child: "Child", filename: str) -> Path | None:
    """Return an absolute path under the kid's spellbee dir for `filename`,
    or None. Rejects any path that escapes the directory (traversal guard)."""
    if not filename or "/" in filename or "\\" in filename or filename.startswith("."):
        return None
    root = _dir_for(child)
    candidate = (root / filename).resolve()
    try:
        candidate.relative_to(root.resolve())
    except ValueError:
        return None
    if not candidate.exists() or not candidate.is_file():
        return None
    if candidate.suffix.lower() not in ALLOWED_EXT:
        return None
    return candidate


_LIST_REF_RE = re.compile(r"\blist\s*[-#]?\s*(\d{1,3})\b", re.IGNORECASE)


def detect_list_reference(*texts: str | None) -> int | None:
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
