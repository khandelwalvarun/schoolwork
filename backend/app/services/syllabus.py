"""Syllabus layer — loads parsed JSONs from data/syllabus/ and answers cycle/topic queries.

Dormant until PDFs are parsed via scripts/parse_syllabus.py. All functions degrade
gracefully to None / empty when JSONs are absent.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Any

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


def fuzzy_topic_for(class_level: int, subject: str | None, title: str | None) -> str | None:
    """Best-effort match of an assignment title to a syllabus topic in the same subject.
    Returns the first topic that shares ≥1 keyword (word ≥4 chars, case-insensitive).
    No-op if the syllabus file isn't loaded."""
    if not subject or not title:
        return None
    syl = load_syllabus(class_level)
    cycles = syl.get("cycles", [])
    title_words = {w.lower() for w in title.split() if len(w) >= 4}
    if not title_words:
        return None
    for c in cycles:
        topics = c.get("topics_by_subject", {}).get(subject, []) or []
        for t in topics:
            t_words = {w.lower() for w in t.split() if len(w) >= 4}
            if title_words & t_words:
                return f"{c.get('name','?')}: {t}"
    return None
