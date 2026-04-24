"""Per-install UI preferences — collapsed sections, section ordering,
anything else the frontend wants to remember across sessions.

Stored as a single JSON file at `data/ui_prefs.json` so it survives server
restarts, is easy to inspect, and doesn't need its own table.
"""
from __future__ import annotations

import json
import tempfile
import threading
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
_PREFS_PATH = _REPO_ROOT / "data" / "ui_prefs.json"
_LOCK = threading.Lock()

DEFAULTS: dict[str, Any] = {
    "collapsed": {},        # {bucketId: bool}
    "bucket_order": {},     # {childId (str): ["overdue","due_today","upcoming"]}
    "kid_order": [],        # [child_id, ...] — leftover kids rendered in natural order
    # Scraper cadence — hours between scheduled syncs (within active window)
    # and the active window itself (24-hour clock in the configured tz).
    "sync_interval_hours": 1,
    "sync_window_start_hour": 8,
    "sync_window_end_hour": 22,
}


def load_prefs() -> dict[str, Any]:
    try:
        if _PREFS_PATH.exists():
            data = json.loads(_PREFS_PATH.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                # Merge with defaults so new keys appear for old users
                out = {**DEFAULTS, **data}
                # Ensure sub-dicts remain dicts/lists even if stored missing.
                if not isinstance(out.get("collapsed"), dict):
                    out["collapsed"] = {}
                if not isinstance(out.get("bucket_order"), dict):
                    out["bucket_order"] = {}
                if not isinstance(out.get("kid_order"), list):
                    out["kid_order"] = []
                return out
    except Exception:
        pass
    return {**DEFAULTS}


def save_prefs(prefs: dict[str, Any]) -> dict[str, Any]:
    merged = load_prefs()
    # Shallow merge — top-level keys overwrite; unknown keys preserved.
    for k, v in (prefs or {}).items():
        if k in DEFAULTS:
            merged[k] = v
        else:
            merged[k] = v  # allow unknown keys too; future-proofing
    with _LOCK:
        _PREFS_PATH.parent.mkdir(parents=True, exist_ok=True)
        # Atomic write: temp in same dir then rename
        with tempfile.NamedTemporaryFile(
            "w", delete=False, dir=_PREFS_PATH.parent, encoding="utf-8"
        ) as f:
            json.dump(merged, f, indent=2, ensure_ascii=False)
            tmp = f.name
        Path(tmp).replace(_PREFS_PATH)
    return merged
