"""Syllabus layer — loads parsed JSONs from data/syllabus/ and answers cycle/topic queries.

Overrides: DB-backed adjustments (calibration UI) are merged on top of the JSON —
cycle date boundaries can be shifted, and topics can be marked covered/skipped/delayed.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

ROOT = Path(__file__).resolve().parent.parent.parent.parent
SYLLABUS_DIR = ROOT / "data" / "syllabus"


@dataclass
class LearningCycle:
    name: str               # e.g. "LC1"
    start: date
    end: date
    topics_by_subject: dict[str, list[str]]


def _class_file(class_level: int) -> Path:
    return SYLLABUS_DIR / f"class_{class_level}_2026-27.json"


@lru_cache(maxsize=8)
def load_syllabus(class_level: int) -> dict[str, Any]:
    p = _class_file(class_level)
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def cycles_for(class_level: int) -> list[LearningCycle]:
    syl = load_syllabus(class_level)
    out: list[LearningCycle] = []
    for c in syl.get("cycles", []):
        try:
            out.append(
                LearningCycle(
                    name=c["name"],
                    start=date.fromisoformat(c["start"]),
                    end=date.fromisoformat(c["end"]),
                    topics_by_subject=c.get("topics_by_subject", {}),
                )
            )
        except Exception:
            continue
    return out


def cycle_for_date(class_level: int, d: date) -> LearningCycle | None:
    for c in cycles_for(class_level):
        if c.start <= d <= c.end:
            return c
    return None


def normalize_subject(subject: str | None) -> str | None:
    """Veracross often prefixes the subject with the class section,
    e.g. "6B Mathematics" or "4C English". Strip that prefix so it matches
    the keys in the syllabus JSON (which are just "Mathematics", "English", …).
    """
    if not subject:
        return subject
    import re
    m = re.match(r"^\s*\d+[A-Z]\s+(.*)$", subject.strip())
    if m:
        return m.group(1).strip()
    return subject.strip()


def fuzzy_topic_for(class_level: int, subject: str | None, title: str | None) -> str | None:
    """Best-effort match of an assignment title to a syllabus topic in the same subject.
    Returns the first topic that shares ≥1 keyword (word ≥4 chars, case-insensitive).
    No-op if the syllabus file isn't loaded."""
    if not subject or not title:
        return None
    subj = normalize_subject(subject) or subject
    syl = load_syllabus(class_level)
    cycles = syl.get("cycles", [])
    title_words = {w.lower() for w in title.split() if len(w) >= 4}
    if not title_words:
        return None
    for c in cycles:
        topics_map = c.get("topics_by_subject", {}) or {}
        # Match normalized or original subject key
        topics = topics_map.get(subj, []) or topics_map.get(subject, []) or []
        for t in topics:
            t_words = {w.lower() for w in t.split() if len(w) >= 4}
            if title_words & t_words:
                return f"{c.get('name','?')}: {t}"
    return None


async def _cycle_overrides(session: AsyncSession, class_level: int) -> dict[str, dict[str, str | None]]:
    from ..models import SyllabusCycleOverride
    rows = (
        await session.execute(
            select(SyllabusCycleOverride).where(SyllabusCycleOverride.class_level == class_level)
        )
    ).scalars().all()
    return {
        r.cycle_name: {"start": r.start_date, "end": r.end_date, "note": r.note}
        for r in rows
    }


async def _topic_status(session: AsyncSession, class_level: int) -> dict[tuple[str, str], dict[str, str | None]]:
    from ..models import SyllabusTopicStatus
    rows = (
        await session.execute(
            select(SyllabusTopicStatus).where(SyllabusTopicStatus.class_level == class_level)
        )
    ).scalars().all()
    return {(r.subject, r.topic): {"status": r.status, "note": r.note} for r in rows}


async def merged_syllabus(session: AsyncSession, class_level: int) -> dict[str, Any]:
    """Return the JSON syllabus with overrides merged in:
       cycles[i].start/end get overridden if an override row exists;
       cycles[i].topic_status[subject][topic] = {status, note} where set."""
    base = dict(load_syllabus(class_level))
    cyc_over = await _cycle_overrides(session, class_level)
    topic_over = await _topic_status(session, class_level)
    merged_cycles: list[dict[str, Any]] = []
    for c in base.get("cycles", []):
        cc = dict(c)
        ov = cyc_over.get(cc.get("name"))
        if ov:
            if ov.get("start"):
                cc["start"] = ov["start"]
            if ov.get("end"):
                cc["end"] = ov["end"]
            if ov.get("note"):
                cc["override_note"] = ov["note"]
            cc["overridden"] = True
        if topic_over:
            ts: dict[str, dict[str, dict[str, str | None]]] = {}
            for subj, topics in (cc.get("topics_by_subject") or {}).items():
                sub: dict[str, dict[str, str | None]] = {}
                for t in topics:
                    key = (subj, t)
                    if key in topic_over:
                        sub[t] = topic_over[key]
                if sub:
                    ts[subj] = sub
            if ts:
                cc["topic_status"] = ts
        merged_cycles.append(cc)
    base["cycles"] = merged_cycles
    return base


async def cycle_for_date_merged(
    session: AsyncSession, class_level: int, d: date
) -> LearningCycle | None:
    """Override-aware cycle lookup."""
    merged = await merged_syllabus(session, class_level)
    for c in merged.get("cycles", []):
        try:
            start = date.fromisoformat(c["start"])
            end = date.fromisoformat(c["end"])
        except Exception:
            continue
        if start <= d <= end:
            return LearningCycle(
                name=c["name"], start=start, end=end,
                topics_by_subject=c.get("topics_by_subject", {}),
            )
    return None


async def upsert_cycle_override(
    session: AsyncSession,
    class_level: int,
    cycle_name: str,
    start: str | None,
    end: str | None,
    note: str | None = None,
) -> dict[str, Any]:
    from ..models import SyllabusCycleOverride
    existing = (
        await session.execute(
            select(SyllabusCycleOverride)
            .where(SyllabusCycleOverride.class_level == class_level)
            .where(SyllabusCycleOverride.cycle_name == cycle_name)
        )
    ).scalar_one_or_none()
    if start is None and end is None and note is None and existing is not None:
        await session.delete(existing)
        await session.commit()
        return {"status": "deleted", "class_level": class_level, "cycle_name": cycle_name}
    if existing is None:
        existing = SyllabusCycleOverride(class_level=class_level, cycle_name=cycle_name)
        session.add(existing)
    existing.start_date = start
    existing.end_date = end
    existing.note = note
    await session.commit()
    return {
        "status": "ok",
        "class_level": class_level,
        "cycle_name": cycle_name,
        "start": start,
        "end": end,
        "note": note,
    }


async def upsert_topic_status(
    session: AsyncSession,
    class_level: int,
    subject: str,
    topic: str,
    status: str | None,
    note: str | None = None,
) -> dict[str, Any]:
    from ..models import SyllabusTopicStatus
    existing = (
        await session.execute(
            select(SyllabusTopicStatus)
            .where(SyllabusTopicStatus.class_level == class_level)
            .where(SyllabusTopicStatus.subject == subject)
            .where(SyllabusTopicStatus.topic == topic)
        )
    ).scalar_one_or_none()
    if status is None:
        if existing is not None:
            await session.delete(existing)
            await session.commit()
        return {"status": "deleted", "class_level": class_level, "subject": subject, "topic": topic}
    if status not in {"covered", "skipped", "delayed", "in_progress"}:
        raise ValueError(f"invalid status: {status}")
    if existing is None:
        existing = SyllabusTopicStatus(
            class_level=class_level, subject=subject, topic=topic, status=status, note=note
        )
        session.add(existing)
    else:
        existing.status = status
        existing.note = note
    await session.commit()
    return {
        "status": "ok",
        "class_level": class_level,
        "subject": subject,
        "topic": topic,
        "topic_status": status,
        "note": note,
    }
