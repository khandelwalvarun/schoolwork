"""Disk cache for the Sunday and PTM briefs.

Both briefs cost ~30s of Claude time per kid. Generating on every page
load wastes the parent's time and burns Max-subscription quota. So we
pre-warm the cache nightly at 02:00 IST (jobs/brief_warmup_job.py)
and the API endpoints read from disk first, falling back to a live
build only on cache miss / forced refresh.

Layout:
  data/cached_briefs/
    sunday/
      <child_slug>_<YYYY-MM-DD>.json   # SundayBrief.to_dict() payload
      <child_slug>_<YYYY-MM-DD>.md     # rendered markdown
    ptm/
      <child_slug>_<YYYY-MM-DD>.json   # PTMBrief.to_dict() payload
      <child_slug>_<YYYY-MM-DD>.md     # rendered markdown

The most-recent file for a kid is what the API serves. We don't
bother with a sliding-window TTL: the file's date IS the freshness.
A `MAX_AGE_DAYS` guard rejects files older than the threshold so a
botched cron + a 4-day-stale brief don't quietly keep serving.

`prune_old(max_keep=30)` drops files older than 30 days so the
directory doesn't grow forever.
"""
from __future__ import annotations

import json
import logging
import re
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from ..config import REPO_ROOT


log = logging.getLogger(__name__)


_BASE = REPO_ROOT / "data" / "cached_briefs"
MAX_AGE_DAYS = 2  # files older than this aren't served as "current"


def _slug(s: str) -> str:
    s = (s or "").strip().lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-") or "unknown"


def _kind_dir(kind: str) -> Path:
    return _BASE / kind


def _paths_for(kind: str, child_slug: str, d: date) -> tuple[Path, Path]:
    base = _kind_dir(kind) / f"{child_slug}_{d.isoformat()}"
    return Path(str(base) + ".json"), Path(str(base) + ".md")


def write_brief(
    kind: str,
    child_slug: str,
    d: date,
    payload: dict[str, Any],
    markdown: str,
) -> tuple[Path, Path]:
    """Persist both JSON and markdown for the cache entry."""
    json_path, md_path = _paths_for(kind, child_slug, d)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(
        json.dumps(payload, default=str, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    md_path.write_text(markdown, encoding="utf-8")
    return json_path, md_path


def read_latest(
    kind: str,
    child_slug: str,
    *,
    today: date,
    max_age_days: int = MAX_AGE_DAYS,
) -> dict[str, Any] | None:
    """Return the most-recent cached JSON for this kid, if it's
    within `max_age_days` of `today`. None on miss / stale / corrupt."""
    folder = _kind_dir(kind)
    if not folder.exists():
        return None
    candidates = sorted(folder.glob(f"{child_slug}_*.json"), reverse=True)
    for path in candidates:
        try:
            stem = path.stem
            date_str = stem.rsplit("_", 1)[-1]
            d = date.fromisoformat(date_str)
        except Exception:
            continue
        if (today - d).days > max_age_days:
            return None
        if d > today:
            # Future-dated cache (clock skew) — skip.
            continue
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception as e:
            log.warning("cached brief unreadable %s: %s", path, e)
            return None
    return None


def read_latest_markdown(
    kind: str,
    child_slug: str,
    *,
    today: date,
    max_age_days: int = MAX_AGE_DAYS,
) -> str | None:
    """Same as read_latest but returns the .md sibling."""
    folder = _kind_dir(kind)
    if not folder.exists():
        return None
    candidates = sorted(folder.glob(f"{child_slug}_*.md"), reverse=True)
    for path in candidates:
        try:
            stem = path.stem
            date_str = stem.rsplit("_", 1)[-1]
            d = date.fromisoformat(date_str)
        except Exception:
            continue
        if (today - d).days > max_age_days:
            return None
        if d > today:
            continue
        try:
            return path.read_text(encoding="utf-8")
        except Exception as e:
            log.warning("cached brief md unreadable %s: %s", path, e)
            return None
    return None


def prune_old(max_keep_days: int = 30) -> int:
    """Drop cache files older than `max_keep_days`. Returns count
    removed. Called from the nightly warmup so the directory doesn't
    accumulate forever."""
    if not _BASE.exists():
        return 0
    cutoff = date.today() - timedelta(days=max_keep_days)
    removed = 0
    for kind_dir in _BASE.iterdir():
        if not kind_dir.is_dir():
            continue
        for f in kind_dir.iterdir():
            try:
                stem = f.stem
                date_str = stem.rsplit("_", 1)[-1]
                d = date.fromisoformat(date_str)
            except Exception:
                continue
            if d < cutoff:
                try:
                    f.unlink()
                    removed += 1
                except Exception:
                    pass
    return removed


def child_slug_for(name: str | None, child_id: int) -> str:
    """Stable slug — uses display_name when present, child id otherwise.
    Same shape across the brief services so reads + writes line up."""
    if name and name.strip():
        return _slug(name)
    return f"child{child_id}"


def freshness_label(today: date, generated_for_iso: str | None) -> str:
    """Human-readable freshness for the API response — e.g.
    'today', 'yesterday', '3 days ago'."""
    if not generated_for_iso:
        return "unknown"
    try:
        d = date.fromisoformat(generated_for_iso)
    except Exception:
        return "unknown"
    age = (today - d).days
    if age == 0:
        return "today"
    if age == 1:
        return "yesterday"
    return f"{age} days ago"
