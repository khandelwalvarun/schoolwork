"""Filesystem-backed listing for the portal-harvested resource files.

Unlike assignment attachments (tracked in the `attachments` DB table and
linked to a veracross_item), resources live purely on disk at:

    data/rawdata/<kid_slug>/<category>/            # per-kid
    data/rawdata/schoolwide/<category>/            # shared

Each `<category>` is one of: attachments, reading, spellbee, syllabus,
news, misc, schedules, assessments, general (extensible — this module
just lists whatever sub-dirs exist).

Nothing here touches SQLite — the filesystem is the source of truth
(that's the whole point of the rawdata layout). This service is what
the /api/resources endpoint, MCP tools, and the frontend Resources
page rely on.
"""
from __future__ import annotations

import mimetypes
import re
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from ..util import paths as P

if TYPE_CHECKING:
    from ..models import Child

ALLOWED_EXT = {
    ".pdf", ".txt", ".md", ".docx", ".doc", ".xlsx", ".xls",
    ".pptx", ".ppt", ".jpg", ".jpeg", ".png", ".gif", ".webp",
    ".csv", ".zip",
}


_EXT_MIME = {
    ".pdf": "application/pdf",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".xls": "application/vnd.ms-excel",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ".csv": "text/csv",
    ".txt": "text/plain",
    ".md": "text/markdown",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".zip": "application/zip",
}


@dataclass(frozen=True)
class ResourceFile:
    scope: str              # 'schoolwide' | 'kid'
    kid_slug: str | None    # set only when scope='kid'
    child_id: int | None
    category: str           # e.g. 'news', 'reading', 'schedules'
    filename: str
    size_bytes: int
    mime_type: str
    modified_at: float      # epoch seconds

    def to_dict(self) -> dict:
        return {
            "scope": self.scope,
            "kid_slug": self.kid_slug,
            "child_id": self.child_id,
            "category": self.category,
            "filename": self.filename,
            "size_bytes": self.size_bytes,
            "mime_type": self.mime_type,
            "modified_at": self.modified_at,
            "download_url": (
                f"/api/resources/file/schoolwide/{self.category}/{self.filename}"
                if self.scope == "schoolwide"
                else f"/api/resources/file/kid/{self.child_id}/{self.category}/{self.filename}"
            ),
        }


def _mime(path: Path) -> str:
    ext = path.suffix.lower()
    if ext in _EXT_MIME:
        return _EXT_MIME[ext]
    guess = mimetypes.guess_type(path.name)[0]
    return guess or "application/octet-stream"


def _scan_dir(
    scope: str,
    base: Path,
    category: str,
    child_id: int | None,
    kid_slug: str | None,
) -> list[ResourceFile]:
    out: list[ResourceFile] = []
    if not base.exists():
        return out
    for p in base.iterdir():
        if not p.is_file():
            continue
        if p.suffix.lower() not in ALLOWED_EXT:
            continue
        try:
            st = p.stat()
        except OSError:
            continue
        out.append(ResourceFile(
            scope=scope, kid_slug=kid_slug, child_id=child_id,
            category=category, filename=p.name,
            size_bytes=st.st_size, mime_type=_mime(p),
            modified_at=st.st_mtime,
        ))
    out.sort(key=lambda f: f.filename.lower())
    return out


def list_schoolwide() -> dict[str, list[ResourceFile]]:
    """Return {category: [ResourceFile]} for all schoolwide resources."""
    root = P.schoolwide_root()
    buckets: dict[str, list[ResourceFile]] = {}
    if not root.exists():
        return buckets
    for cat_dir in sorted(root.iterdir()):
        if not cat_dir.is_dir():
            continue
        files = _scan_dir("schoolwide", cat_dir, cat_dir.name, None, None)
        if files:
            buckets[cat_dir.name] = files
    return buckets


def list_for_kid(child: "Child") -> dict[str, list[ResourceFile]]:
    """Return {category: [ResourceFile]} for one child's per-kid resources.
    Skips 'attachments' since those are already listed via /api/attachments
    — including them here would double-count them in the UI."""
    root = P.kid_root(child)
    slug = P.kid_slug(child)
    buckets: dict[str, list[ResourceFile]] = {}
    if not root.exists():
        return buckets
    for cat_dir in sorted(root.iterdir()):
        if not cat_dir.is_dir():
            continue
        if cat_dir.name == "attachments":
            continue
        files = _scan_dir("kid", cat_dir, cat_dir.name, child.id, slug)
        if files:
            buckets[cat_dir.name] = files
    return buckets


def list_everything(children: list["Child"]) -> dict:
    return {
        "schoolwide": {k: [f.to_dict() for f in v] for k, v in list_schoolwide().items()},
        "kids": [
            {
                "child_id": c.id,
                "display_name": c.display_name,
                "kid_slug": P.kid_slug(c),
                "by_category": {
                    k: [f.to_dict() for f in v]
                    for k, v in list_for_kid(c).items()
                },
            }
            for c in children
        ],
    }


# ─── file resolution + traversal guard ──────────────────────────────────────

_SAFE_NAME = re.compile(r"^[A-Za-z0-9 _.,\-()\[\]&+%'’–—]+$")


def _safe_segment(s: str) -> bool:
    if not s or s in (".", "..") or "/" in s or "\\" in s:
        return False
    return True


def resolve_schoolwide(category: str, filename: str) -> Path | None:
    if not _safe_segment(category) or not _safe_segment(filename):
        return None
    base = P.schoolwide_root() / category
    candidate = (base / filename).resolve()
    try:
        candidate.relative_to(P.rawdata_root().resolve())
    except ValueError:
        return None
    if not candidate.exists() or not candidate.is_file():
        return None
    if candidate.suffix.lower() not in ALLOWED_EXT:
        return None
    return candidate


def resolve_kid(child: "Child", category: str, filename: str) -> Path | None:
    if not _safe_segment(category) or not _safe_segment(filename):
        return None
    base = P.kid_root(child) / category
    candidate = (base / filename).resolve()
    try:
        candidate.relative_to(P.rawdata_root().resolve())
    except ValueError:
        return None
    if not candidate.exists() or not candidate.is_file():
        return None
    if candidate.suffix.lower() not in ALLOWED_EXT:
        return None
    return candidate
