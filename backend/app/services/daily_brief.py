"""Daily brief — one-paragraph synthesis for the Today page.

The Sunday brief's lighter sibling. Runs every morning (or every page
load on Today). Per kid: 1-2 sentences naming what matters in the
next ~48 hours, optionally one focused parent-action.

Why a separate service from sunday_brief.py:
- Different time horizon: today + tomorrow + day-after, not the whole
  cycle. Most §1 of the Sunday brief (cycle progress, slope, Excellence
  arithmetic) would be noise on a daily surface.
- Different data pack: leaner, no recent-grades trajectory, no shaky
  ranking — just upcoming/overdue/due-today + any grades that landed
  in the last 24h.
- Different output schema: 1-2 sentences, not 4 sections.

Like sunday_brief.py, the LLM (claude_cli backend) is the synthesizer;
the data pack is built deterministically and every cited row id must
appear in pack['_row_ids']. If Claude is unreachable / invalid, we
fall back to a rule-based one-line summary that's mechanical but
correct.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..llm.client import LLMClient
from ..models import Child, VeracrossItem
from ..util.time import today_ist
from .grade_match import _parse_loose_date
from .syllabus import normalize_subject


log = logging.getLogger(__name__)


@dataclass
class DailyBrief:
    child_id: int
    child_name: str
    generated_for: str                  # ISO date
    summary: str                        # the 1-2 sentence prose
    has_signal: bool                    # False = nothing worth surfacing
    pack_row_ids: list[int]             # for client-side debug

    def to_dict(self) -> dict[str, Any]:
        return {
            "child_id": self.child_id,
            "child_name": self.child_name,
            "generated_for": self.generated_for,
            "summary": self.summary,
            "has_signal": self.has_signal,
            "pack_row_ids": self.pack_row_ids,
        }


CLOSED_PORTAL = {"submitted", "graded", "dismissed"}
CLOSED_PARENT = {"submitted", "graded", "done_at_home"}


def _is_closed(it: VeracrossItem) -> bool:
    if it.status in CLOSED_PORTAL:
        return True
    if it.parent_status in CLOSED_PARENT:
        return True
    return False


async def _build_daily_pack(
    session: AsyncSession,
    child: Child,
    today: date,
) -> dict[str, Any]:
    """Lean data pack: items due in [today, today+2], overdue, and any
    grade rows that landed yesterday/today."""
    items = (
        await session.execute(
            select(VeracrossItem)
            .where(VeracrossItem.child_id == child.id)
            .where(VeracrossItem.kind.in_(("assignment", "grade")))
        )
    ).scalars().all()

    overdue: list[dict[str, Any]] = []
    due_today: list[dict[str, Any]] = []
    due_tomorrow: list[dict[str, Any]] = []
    due_day_after: list[dict[str, Any]] = []
    recent_grades: list[dict[str, Any]] = []

    for r in items:
        d = _parse_loose_date(r.due_or_date)
        if d is None:
            continue
        subj = normalize_subject(r.subject) or r.subject

        if r.kind == "assignment":
            if _is_closed(r):
                continue
            payload = {
                "row_id": r.id,
                "subject": subj,
                "title": r.title,
                "due": d.isoformat(),
                "body": (r.body or "")[:400],  # cap so prompt doesn't bloat
            }
            days = (d - today).days
            if days < 0:
                payload["days_overdue"] = -days
                overdue.append(payload)
            elif days == 0:
                due_today.append(payload)
            elif days == 1:
                due_tomorrow.append(payload)
            elif days == 2:
                due_day_after.append(payload)
        elif r.kind == "grade":
            ago = (today - d).days
            if 0 <= ago <= 1:
                pct = None
                try:
                    n = json.loads(r.normalized_json or "{}")
                    if n.get("grade_pct") is not None:
                        pct = float(n["grade_pct"])
                except Exception:
                    pass
                recent_grades.append({
                    "row_id": r.id,
                    "subject": subj,
                    "title": r.title,
                    "graded_date": d.isoformat(),
                    "pct": pct,
                })

    overdue.sort(key=lambda x: -int(x.get("days_overdue", 0)))

    pack: dict[str, Any] = {
        "child": {
            "id": child.id,
            "name": child.display_name,
            "class_section": child.class_section,
            "class_level": child.class_level,
        },
        "today": today.isoformat(),
        "overdue": overdue[:6],
        "due_today": due_today,
        "due_tomorrow": due_tomorrow,
        "due_day_after": due_day_after,
        "recent_grades": recent_grades,
    }

    row_ids: set[int] = set()
    for arr in (overdue, due_today, due_tomorrow, due_day_after, recent_grades):
        for it in arr:
            row_ids.add(int(it["row_id"]))
    pack["_row_ids"] = sorted(row_ids)

    return pack


CLAUDE_DAILY_SYSTEM = """You are the synthesizer for a *daily* parent-cockpit brief that shows on the Today page.

ONE child only — never compare. The reader scans this in 5 seconds while making coffee. Your job: ONE short paragraph (1-2 sentences max, ~30 words), focusing on what matters in the next ~48 hours.

You receive a JSON DATA PACK with overdue items, due today/tomorrow/day-after, and any grades that landed yesterday/today. Every numeric or row-id claim in your output must echo a value present in the pack. Don't invent dates, subjects, or counts.

OUTPUT — strict JSON only, matching this schema:

{
  "summary": "<the 1-2 sentence paragraph; ≤ 240 chars; focused; no exclamation marks>",
  "has_signal": <true | false>,
  "evidence_row_ids": [<int>, ...]   // every row id named or implied in the summary
}

Rules:
- has_signal = false (and a one-line summary like "Nothing pressing today.") when:
   - there are no overdue items
   - AND nothing due today/tomorrow/day-after
   - AND no recent grades worth flagging
- Group items by subject when possible — "3 Hindi items due tomorrow" beats "3 items due tomorrow".
- If everything in the next 48h is in one subject, name the subject.
- If a recent grade was striking (very high or very low for the kid), you can mention it briefly.
- No advice, no encouragement, no emojis. Factual and warm.
- Single sentence preferred when possible; only break into two if the second adds essential signal.
- NEVER list row ids in prose; put them all in evidence_row_ids.

Return ONLY the JSON object. No prose, no fences."""


def _validate_daily(out: dict[str, Any], pack: dict[str, Any]) -> str | None:
    if not isinstance(out.get("summary"), str) or not out["summary"].strip():
        return "summary missing"
    if "has_signal" not in out:
        return "has_signal missing"
    valid = set(pack.get("_row_ids", []))
    ids = out.get("evidence_row_ids", [])
    if not isinstance(ids, list):
        return "evidence_row_ids must be list"
    for v in ids:
        try:
            vi = int(v)
        except Exception:
            return f"row id {v!r} is not an int"
        if vi not in valid:
            return f"row id {vi} not in pack"
    if len(out["summary"]) > 280:
        return f"summary too long ({len(out['summary'])} chars > 280)"
    return None


def _rule_fallback_summary(pack: dict[str, Any]) -> tuple[str, bool]:
    """Mechanical 1-line if Claude is down. Adds the bare minimum signal."""
    overdue = pack.get("overdue") or []
    today = pack.get("due_today") or []
    tomorrow = pack.get("due_tomorrow") or []
    day_after = pack.get("due_day_after") or []
    name = pack["child"]["name"]
    parts: list[str] = []
    if overdue:
        parts.append(f"{len(overdue)} overdue")
    if today:
        parts.append(f"{len(today)} due today")
    if tomorrow:
        parts.append(f"{len(tomorrow)} due tomorrow")
    if day_after:
        parts.append(f"{len(day_after)} due day-after")
    if not parts:
        return ("Nothing pressing today.", False)
    return (f"{name}: {', '.join(parts)}.", True)


async def _claude_daily(
    pack: dict[str, Any],
) -> dict[str, Any] | None:
    client = LLMClient()
    if not client.enabled():
        return None
    pack_json = json.dumps(pack, default=str, ensure_ascii=False, indent=2)
    prompt = f"DATA PACK:\n```json\n{pack_json}\n```\n\nGenerate the brief."
    try:
        resp = await client.complete(
            purpose="daily_brief_synthesis",
            system=CLAUDE_DAILY_SYSTEM,
            prompt=prompt,
            max_tokens=320,
        )
    except Exception as e:
        log.warning("daily_brief Claude failed: %s", e)
        return None
    text = (resp.text or "").strip()
    if text.startswith("```"):
        text = text.split("```", 2)
        text = text[1] if len(text) >= 2 else "".join(text)
        if text.lstrip().startswith("json"):
            text = text.split("\n", 1)[1] if "\n" in text else text
    try:
        out = json.loads(text)
    except Exception as e:
        log.warning("daily_brief Claude returned non-JSON: %s; raw=%r", e, text[:200])
        return None
    err = _validate_daily(out, pack)
    if err:
        log.warning("daily_brief Claude validation failed: %s", err)
        return None
    return out


# ─── cache ──────────────────────────────────────────────────────────────────
#
# In-memory cache keyed by (child_id, generated_for_iso). The brief is
# stable across a day for a given kid as long as the underlying data
# doesn't change, so cache hits are the common case. Sync completion
# invalidates the cache (sync_job.py calls invalidate_daily_brief_cache).
# Restarts naturally drop the cache, which is fine — a re-build is ~30s.

_BRIEF_CACHE: dict[tuple[int, str], DailyBrief] = {}


def invalidate_daily_brief_cache(child_id: int | None = None) -> int:
    """Drop cached briefs. Pass `child_id` to drop just that kid's row.
    Returns the number of entries removed. Called by sync_job after a
    successful sync so the next page load reflects fresh data."""
    if child_id is None:
        n = len(_BRIEF_CACHE)
        _BRIEF_CACHE.clear()
        return n
    keys = [k for k in _BRIEF_CACHE if k[0] == child_id]
    for k in keys:
        _BRIEF_CACHE.pop(k, None)
    return len(keys)


async def build_daily_brief(
    session: AsyncSession,
    child: Child,
    *,
    today: date | None = None,
    use_claude: bool = True,
    use_cache: bool = True,
) -> DailyBrief:
    today = today or today_ist()
    today_iso = today.isoformat()
    cache_key = (child.id, today_iso)

    if use_cache and cache_key in _BRIEF_CACHE:
        return _BRIEF_CACHE[cache_key]

    pack = await _build_daily_pack(session, child, today)

    if use_claude:
        out = await _claude_daily(pack)
        if out is not None:
            brief = DailyBrief(
                child_id=child.id,
                child_name=child.display_name,
                generated_for=today_iso,
                summary=out["summary"].strip(),
                has_signal=bool(out.get("has_signal", True)),
                pack_row_ids=pack["_row_ids"],
            )
            if use_cache:
                _BRIEF_CACHE[cache_key] = brief
            return brief

    summary, has_signal = _rule_fallback_summary(pack)
    brief = DailyBrief(
        child_id=child.id,
        child_name=child.display_name,
        generated_for=today_iso,
        summary=summary,
        has_signal=has_signal,
        pack_row_ids=pack["_row_ids"],
    )
    # Cache the rule-fallback only briefly — if Claude comes back, we
    # want to upgrade the next call. A separate "fallback" cache slot
    # would be cleaner but the simpler "cache anything" approach is
    # acceptable since a fallback usually means LLM is broken anyway.
    if use_cache:
        _BRIEF_CACHE[cache_key] = brief
    return brief


async def build_daily_brief_for_all(
    session: AsyncSession,
    *,
    today: date | None = None,
    use_claude: bool = True,
) -> list[DailyBrief]:
    children = (await session.execute(select(Child))).scalars().all()
    out: list[DailyBrief] = []
    for c in children:
        out.append(await build_daily_brief(session, c, today=today, use_claude=use_claude))
    return out
