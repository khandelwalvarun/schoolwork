"""LLM-backed annotations for trends. Short, cached-on-key, degrades to empty
strings if no LLM is configured."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from ..config import get_settings
from ..llm.client import LLMClient
from . import queries as Q
from . import syllabus as syl


_PROMPT_DIR = Path(__file__).resolve().parent.parent / "llm" / "prompts"


async def annotate_grade_trends(
    session: AsyncSession, child_id: int
) -> list[dict[str, Any]]:
    """For each subject trend, produce a one-line annotation referencing the
    current syllabus cycle when possible. Returns the trend rows with
    `annotation` appended. Falls back to a deterministic blurb if no LLM."""
    trends = await Q.get_grade_trends(session, child_id)
    if not trends:
        return []

    from ..models import Child
    from sqlalchemy import select
    child = (
        await session.execute(select(Child).where(Child.id == child_id))
    ).scalar_one_or_none()
    class_level = child.class_level if child else None

    from datetime import date as _date
    today_d = _date.today()
    cycle = None
    prev_cycle = None
    if class_level is not None:
        cycles = syl.cycles_for(class_level)
        for i, c in enumerate(cycles):
            if c.start <= today_d <= c.end:
                cycle = c
                if i > 0:
                    prev_cycle = cycles[i - 1]
                break

    client = LLMClient()
    settings = get_settings()
    try:
        system = (_PROMPT_DIR / "grade_trend_annotation.md").read_text(encoding="utf-8")
    except FileNotFoundError:
        system = ""

    out: list[dict[str, Any]] = []
    for t in trends:
        if t.get("count", 0) < 2:
            t = {**t, "annotation": "Not enough grades yet."}
            out.append(t)
            continue
        # Deterministic fallback — used when LLM disabled/errors.
        arrow = t.get("arrow") or ""
        subj = t.get("subject") or "Subject"
        latest = t.get("latest")
        fallback = f"{subj} {arrow} latest {int(latest)}% (n={t.get('count')})."
        ann = fallback
        if client.enabled() and system:
            facts = {
                "subject": subj,
                "latest": latest,
                "avg": t.get("avg"),
                "arrow": arrow,
                "count": t.get("count"),
                "recent": [g.get("grade_pct") for g in t.get("recent", [])],
                "current_cycle": None if cycle is None else {
                    "name": cycle.name,
                    "topics": (cycle.topics_by_subject.get(subj) or [])[:12],
                },
                "previous_cycle": None if prev_cycle is None else {
                    "name": prev_cycle.name,
                    "topics": (prev_cycle.topics_by_subject.get(subj) or [])[:12],
                },
            }
            try:
                resp = await client.complete(
                    purpose="grade_trend_annotation",
                    model=settings.claude_cli_model or None,
                    system=system,
                    prompt="Facts (JSON):\n" + json.dumps(facts, ensure_ascii=False),
                    max_tokens=80,
                    extra_cache_key=f"{child_id}:{subj}:{int(latest or 0)}:{arrow}",
                )
                text = (resp.text or "").strip().replace("\n", " ")
                if text:
                    ann = text[:200]
            except Exception:
                pass
        out.append({**t, "annotation": ann})
    return out
