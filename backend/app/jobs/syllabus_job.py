"""Weekly syllabus recheck — re-downloads the class syllabi from Drive,
re-extracts JSON, and creates a `syllabus_changed` event when the parsed
JSON differs from what we already have.

Wired into APScheduler by jobs/scheduler.py.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from ..db import get_async_session
from ..models import Event
from ..notability import rubric as R
from ..notability.dispatcher import dispatch_event

log = logging.getLogger(__name__)


REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
SYLLABUS_DIR = REPO_ROOT / "data" / "syllabus"
CACHE_DIR = SYLLABUS_DIR / ".cache"


def _read_existing(class_level: int) -> dict[str, Any] | None:
    p = SYLLABUS_DIR / f"class_{class_level}_2026-27.json"
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def _diff_syllabus(
    old: dict[str, Any] | None, new: dict[str, Any]
) -> dict[str, Any]:
    """Return a summary dict describing what changed between old and new."""
    out: dict[str, Any] = {
        "cycles_added": [],
        "cycles_removed": [],
        "cycle_date_changes": [],
        "topics_added": {},    # {"<cycle>.<subject>": [topic, ...]}
        "topics_removed": {},
    }
    if old is None:
        new_cycle_names = [c.get("name") for c in new.get("cycles", [])]
        out["cycles_added"] = new_cycle_names
        return out

    old_cycles = {c["name"]: c for c in old.get("cycles", []) if "name" in c}
    new_cycles = {c["name"]: c for c in new.get("cycles", []) if "name" in c}

    out["cycles_added"] = [n for n in new_cycles if n not in old_cycles]
    out["cycles_removed"] = [n for n in old_cycles if n not in new_cycles]

    for name in old_cycles.keys() & new_cycles.keys():
        o, n = old_cycles[name], new_cycles[name]
        if o.get("start") != n.get("start") or o.get("end") != n.get("end"):
            out["cycle_date_changes"].append({
                "cycle": name,
                "old": {"start": o.get("start"), "end": o.get("end")},
                "new": {"start": n.get("start"), "end": n.get("end")},
            })
        old_topics = o.get("topics_by_subject") or {}
        new_topics = n.get("topics_by_subject") or {}
        for subj in set(old_topics) | set(new_topics):
            old_set = set(old_topics.get(subj, []))
            new_set = set(new_topics.get(subj, []))
            added = sorted(new_set - old_set)
            removed = sorted(old_set - new_set)
            if added:
                out["topics_added"][f"{name}.{subj}"] = added
            if removed:
                out["topics_removed"][f"{name}.{subj}"] = removed
    return out


def _diff_is_empty(d: dict[str, Any]) -> bool:
    return not (
        d["cycles_added"] or d["cycles_removed"] or d["cycle_date_changes"]
        or d["topics_added"] or d["topics_removed"]
    )


async def check_syllabus_updates(class_levels: tuple[int, ...] = (4, 6)) -> dict[str, Any]:
    """Re-download + re-parse each class's syllabus; if the result differs
    from the stored copy, persist a `syllabus_changed` event and dispatch it
    through the normal channel policy. Returns a summary."""
    # Import lazily — the fetch script pulls heavy deps (pypdf, httpx) and
    # we don't want the scheduler import to fail if they're missing.
    try:
        from ...scripts import fetch_syllabus as fs  # type: ignore[import-not-found]
    except Exception:
        import sys as _sys
        _sys.path.insert(0, str(REPO_ROOT))
        from backend.scripts import fetch_syllabus as fs  # type: ignore

    summary: dict[str, Any] = {"classes": [], "events_created": 0}
    for cl in class_levels:
        entry: dict[str, Any] = {"class_level": cl, "status": "unchanged"}
        try:
            old = _read_existing(cl)
            # Force re-download: wipe cached PDF so process_class doesn't
            # reuse last week's file
            cached_pdf = CACHE_DIR / f"class_{cl}.pdf"
            if cached_pdf.exists():
                cached_pdf.unlink()
            await fs.process_class(cl)
            new = _read_existing(cl)
            if new is None:
                entry["status"] = "fetch_failed"
                summary["classes"].append(entry)
                continue
            diff = _diff_syllabus(old, new)
            if _diff_is_empty(diff):
                summary["classes"].append(entry)
                continue
            entry["status"] = "changed"
            entry["diff"] = diff
            # Persist an Event
            ek = R.SYLLABUS_CHANGED
            payload = {"class_level": cl, "diff": diff}
            async with get_async_session() as session:
                stmt = sqlite_insert(Event).values(
                    kind=ek.name,
                    child_id=None,
                    subject=None,
                    related_item_id=None,
                    payload_json=json.dumps(payload, default=str, ensure_ascii=False),
                    notability=ek.notability,
                    dedup_key=ek.dedup_key(class_level=cl, diff_hash=_diff_hash(diff)),
                )
                stmt = stmt.on_conflict_do_nothing(index_elements=[Event.dedup_key])
                await session.execute(stmt)
                await session.commit()
                # Look up the id for dispatch
                ev = (
                    await session.execute(
                        select(Event).where(
                            Event.dedup_key == stmt.compile().params["dedup_key"]
                        )
                    )
                ).scalar_one_or_none()
                if ev is not None:
                    try:
                        await dispatch_event(session, ev.id)
                    except Exception as e:
                        log.warning("dispatch syllabus_changed failed: %s", e)
                    summary["events_created"] += 1
            log.info("syllabus changed for Class %d — event persisted", cl)
        except Exception as e:
            log.warning("syllabus check for Class %d failed: %s", cl, e)
            entry["status"] = "error"
            entry["error"] = str(e)
        summary["classes"].append(entry)
    return summary


def _diff_hash(diff: dict[str, Any]) -> str:
    import hashlib
    return hashlib.sha256(
        json.dumps(diff, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()[:12]


async def run_weekly_syllabus_check() -> None:
    """Entrypoint the scheduler calls."""
    log.info("weekly syllabus check starting")
    r = await check_syllabus_updates()
    changed = [c for c in r["classes"] if c["status"] == "changed"]
    log.info(
        "weekly syllabus check done: %d classes checked, %d changed, %d events",
        len(r["classes"]), len(changed), r["events_created"],
    )
