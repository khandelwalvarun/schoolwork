"""Per-install cache for stable Veracross data — class rosters + grading
period IDs per kid. Persisted to `data/veracross_cache.json` (gitignored).

Why: grading-period IDs (13 for MS, 25/27/31/33 for JS LC1-4) are set at
start-of-year and shift only when the school reconfigures. Re-probing the
enrollment grade_detail page for every sync just to rediscover them is
pointless. Same for class roster. Cache it; let the heavy (weekly) tier
revalidate.

Shape on disk:
{
  "children": {
    "1": {
      "vc_id": "103460",
      "class_ids":      ["138358", "138359", ...],
      "grading_periods": [13, 14, 15, 16],
      "last_revalidated_at": "2026-04-24T..."
    },
    "2": {...}
  },
  "schema_version": 1
}
"""
from __future__ import annotations

import json
import tempfile
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
_CACHE_PATH = _REPO_ROOT / "data" / "veracross_cache.json"
_LOCK = threading.Lock()

# Heavy tier revalidates weekly; anything older than this is treated as stale
# on read (best-effort fallback will rediscover mid-sync if the heavy tier
# hasn't run yet).
STALE_AFTER = timedelta(days=10)


def _load() -> dict[str, Any]:
    if not _CACHE_PATH.exists():
        return {"children": {}, "schema_version": 1}
    try:
        data = json.loads(_CACHE_PATH.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return {"children": {}, "schema_version": 1}
        data.setdefault("children", {})
        return data
    except Exception:
        return {"children": {}, "schema_version": 1}


def _write(data: dict[str, Any]) -> None:
    with _LOCK:
        _CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            "w", delete=False, dir=_CACHE_PATH.parent, encoding="utf-8"
        ) as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
            tmp = f.name
        Path(tmp).replace(_CACHE_PATH)


def get_for_child(child_pk: int) -> dict[str, Any] | None:
    """Return the cached entry for a child (by DB pk). None if absent."""
    return _load().get("children", {}).get(str(child_pk))


def is_stale(child_pk: int) -> bool:
    entry = get_for_child(child_pk)
    if not entry:
        return True
    t = entry.get("last_revalidated_at")
    if not t:
        return True
    try:
        last = datetime.fromisoformat(t)
    except Exception:
        return True
    if last.tzinfo is None:
        last = last.replace(tzinfo=timezone.utc)
    return datetime.now(tz=timezone.utc) - last > STALE_AFTER


def set_for_child(
    child_pk: int,
    vc_id: str,
    class_ids: list[str],
    grading_periods: list[int],
) -> None:
    data = _load()
    data["children"][str(child_pk)] = {
        "vc_id": vc_id,
        "class_ids": list(class_ids),
        "grading_periods": sorted(set(int(p) for p in grading_periods)),
        "last_revalidated_at": datetime.now(tz=timezone.utc).isoformat(),
    }
    _write(data)


def clear_for_child(child_pk: int) -> None:
    data = _load()
    data["children"].pop(str(child_pk), None)
    _write(data)


def clear_all() -> None:
    _write({"children": {}, "schema_version": 1})
