"""Filesystem layout for the cockpit.

Everything persistent lives under `data/` (configurable via DATA_DIR).

    data/
      app.db  app.db-wal  app.db-shm
      storage_state.json
      veracross_creds.json
      veracross_cache.json
      ui_prefs.json
      syllabus/
        class_<N>_<year>.json
      rawdata/
        <kid_slug>/
          attachments/      downloaded PDFs/images from Veracross, named:
                             <yyyy-mm-dd>_<subject>_<title>_<sha8>.<ext>
          spellbee/         Spelling-Bee word lists (per-kid)
          screenshots/      misc. screenshots the parent saves manually

`kid_slug` is `<display_name_lower>_<class_level><class_section>`
(e.g. `samarth_4C`, `tejas_6B`).
"""
from __future__ import annotations

import re
import unicodedata
from pathlib import Path
from typing import Protocol

from ..config import get_settings


class _ChildLike(Protocol):
    id: int
    display_name: str
    class_level: int
    class_section: str | None


# ─── roots ──────────────────────────────────────────────────────────────────

def data_root() -> Path:
    """Absolute path to the data dir. Created if missing."""
    root = Path(get_settings().data_dir)
    root.mkdir(parents=True, exist_ok=True)
    return root


def rawdata_root() -> Path:
    root = data_root() / "rawdata"
    root.mkdir(parents=True, exist_ok=True)
    return root


# ─── slugs ──────────────────────────────────────────────────────────────────

_SLUG_STRIP = re.compile(r"[^a-z0-9]+")


def slugify(s: str, max_len: int = 40) -> str:
    """Lowercase ASCII slug with dashes. Empty string → 'misc'."""
    if not s:
        return "misc"
    # Strip diacritics (café → cafe), collapse non-alnum to dashes
    norm = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("ascii")
    slug = _SLUG_STRIP.sub("-", norm.lower()).strip("-")
    if not slug:
        return "misc"
    return slug[:max_len].rstrip("-") or "misc"


def subject_slug(subject: str | None) -> str:
    """Strip leading class prefix ('4C English' → 'english') before slugging."""
    if not subject:
        return "misc"
    # Drop leading 'NX ' or 'NNX ' token if present (class tag)
    parts = subject.strip().split(None, 1)
    rest = parts[1] if len(parts) == 2 and re.fullmatch(r"\d{1,2}[A-Za-z]?", parts[0]) else subject
    return slugify(rest)


def kid_slug(child: _ChildLike) -> str:
    """Stable per-kid directory name: 'samarth_4C', 'tejas_6B'.

    class_section in the DB is stored with the class-level prefix already
    baked in (e.g. '4C', '6B'), so we use it directly. If it's missing, we
    fall back to the bare class_level."""
    name = slugify(child.display_name or f"child{child.id}", max_len=24)
    section = (child.class_section or "").strip()
    return f"{name}_{section or child.class_level}"


# ─── per-kid directories ────────────────────────────────────────────────────

def kid_root(child: _ChildLike) -> Path:
    p = rawdata_root() / kid_slug(child)
    p.mkdir(parents=True, exist_ok=True)
    return p


def schoolwide_root() -> Path:
    """Per-school (not per-kid) resources: newsletters, time tables,
    handbook, exam schedules, etc."""
    p = rawdata_root() / "schoolwide"
    p.mkdir(parents=True, exist_ok=True)
    return p


def kid_attachments_dir(child: _ChildLike) -> Path:
    p = kid_root(child) / "attachments"
    p.mkdir(parents=True, exist_ok=True)
    return p


def kid_spellbee_dir(child: _ChildLike) -> Path:
    p = kid_root(child) / "spellbee"
    p.mkdir(parents=True, exist_ok=True)
    return p


def kid_screenshots_dir(child: _ChildLike) -> Path:
    p = kid_root(child) / "screenshots"
    p.mkdir(parents=True, exist_ok=True)
    return p


# ─── filename composition ───────────────────────────────────────────────────

def attachment_filename(
    *,
    date_iso: str | None,
    subject: str | None,
    title: str | None,
    sha256_hex: str,
    ext: str,
) -> str:
    """Canonical human-readable name for a downloaded attachment.

    <iso-date>_<subject>_<title>_<sha8>.<ext>

    - date_iso: assignment due date (preferred) or first_seen date. Missing →
      '0000-00-00' so chronological sort still works.
    - subject_slug strips the class prefix.
    - title truncated to 40 chars; ext lowercased and normalized to include the
      leading dot; empty ext is allowed.
    """
    date_part = (date_iso or "0000-00-00")[:10]
    sub = subject_slug(subject)
    ttl = slugify(title or "", max_len=40)
    sha8 = sha256_hex[:8] if sha256_hex else "xxxxxxxx"
    ext = ext.lower().strip()
    if ext and not ext.startswith("."):
        ext = "." + ext
    return f"{date_part}_{sub}_{ttl}_{sha8}{ext}"


# ─── relative-path helpers ──────────────────────────────────────────────────

def repo_relative(path: Path) -> str:
    """Stringify `path` as a repo-relative path, so it's portable across
    machines. Used for `attachments.local_path` and anywhere else we persist
    paths to the DB."""
    from ..config import REPO_ROOT
    try:
        return str(path.resolve().relative_to(REPO_ROOT))
    except ValueError:
        return str(path)
