"""Match grades back to the assignment that produced them.

Why: the school usually grades a worksheet days/weeks after the kid
hands it in. The grade row and the assignment row have no direct
foreign key — only soft signals (same kid, same subject, similar
title, plausible date offset). This module reconciles them so the
cockpit can show "Worksheet on Fractions → 78 %" instead of two
disconnected rows.

Two-pass strategy:

  1. **Deterministic Jaccard** on token-overlap of titles + a
     plausible date window. Cheap, runs every sync. If the best
     candidate's score is comfortably above the runner-up,
     accept it as the link with `match_method='jaccard'`.

  2. **LLM tiebreaker** for ambiguous cases (top two within a small
     margin) — sends the grade title + the top 3 candidates to the
     local Ollama and asks for the index of the best fit. Records
     `match_method='llm'`.

`match_method='manual'` is reserved for an explicit parent override.

The matching is idempotent: rerunning won't re-link already-linked
grades unless the existing link's confidence is below the rerun
threshold.
"""
from __future__ import annotations

import json
import logging
import re
from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import VeracrossItem
from ..util.time import today_ist

log = logging.getLogger(__name__)


# ─── tokenisation + similarity ──────────────────────────────────────────────

_STOP = {
    "a", "an", "the", "of", "for", "on", "in", "to", "and", "or",
    "homework", "hw", "assignment", "worksheet", "exercise", "ex",
    "class", "chapter", "ch", "lesson", "ls", "test", "quiz",
    "lc1", "lc2", "lc3", "lc4", "lc5",
}


def _tokens(s: str | None) -> set[str]:
    if not s:
        return set()
    # Strip parens content and non-alphanumerics; lowercase; drop stopwords + 1-char.
    s = re.sub(r"\(.*?\)", " ", s)
    raw = re.findall(r"[a-z0-9]+", s.lower())
    return {t for t in raw if len(t) > 1 and t not in _STOP}


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


_MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
    "january": 1, "february": 2, "march": 3, "april": 4, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10,
    "november": 11, "december": 12,
}


def _parse_loose_date(s: str | None, ref: date | None = None) -> date | None:
    """Accept ISO 'YYYY-MM-DD' or abbreviated 'Apr 22' / 'April 22' /
    '22 Apr'. For abbreviated forms, assume the year that puts the date
    closest to (and not far in the future of) the reference (default
    today_ist). Returns None on unparseable input."""
    if not s:
        return None
    s = s.strip()
    # ISO
    try:
        return date.fromisoformat(s[:10])
    except ValueError:
        pass
    # 'Apr 22', 'April 22', '22 Apr'
    parts = re.split(r"[\s,/-]+", s)
    parts = [p for p in parts if p]
    month: int | None = None
    day: int | None = None
    year: int | None = None
    for p in parts:
        lp = p.lower()
        if lp in _MONTHS and month is None:
            month = _MONTHS[lp]
        elif p.isdigit():
            n = int(p)
            if 1900 <= n <= 2100 and year is None:
                year = n
            elif 1 <= n <= 31 and day is None:
                day = n
    if month is None or day is None:
        return None
    if year is None:
        ref = ref or today_ist()
        # Pick the year that puts the date <= 6 months before or 1 month after `ref`
        for candidate_year in (ref.year, ref.year - 1):
            try:
                cand = date(candidate_year, month, day)
            except ValueError:
                continue
            if cand <= ref + timedelta(days=30):
                return cand
        return None
    try:
        return date(year, month, day)
    except ValueError:
        return None


def _date_proximity_score(grade_date: str | None, asg_due: str | None) -> float:
    """1.0 if asg.due ≤ grade_date and within 30 days; tapers linearly to 0
    at 60 days; 0 if asg is after grade or > 60 days before. Negative
    boost for same-day (1.05) — same-day matches are rare but very strong."""
    g = _parse_loose_date(grade_date)
    a = _parse_loose_date(asg_due)
    if g is None or a is None:
        return 0.0
    delta = (g - a).days
    if delta < 0:
        return 0.0          # assignment due AFTER grade → impossible match
    if delta == 0:
        return 1.05         # same-day grading is strong signal
    if delta <= 30:
        return 1.0 - (delta / 60)  # 1.0 → 0.5 over 30 days
    if delta <= 60:
        return 0.5 - ((delta - 30) / 60)  # 0.5 → 0 over next 30
    return 0.0


def _score(grade: VeracrossItem, asg: VeracrossItem) -> float:
    """Combined similarity in [0, ~2]. Higher = better. Title match
    dominates (×1.5 weight); date proximity refines."""
    g_tokens = _tokens(grade.title) | _tokens(grade.title_en)
    a_tokens = _tokens(asg.title) | _tokens(asg.title_en)
    title_sim = _jaccard(g_tokens, a_tokens)
    date_score = _date_proximity_score(grade.due_or_date, asg.due_or_date)
    return title_sim * 1.5 + date_score * 0.6


# ─── candidate generation ───────────────────────────────────────────────────

async def _candidates(
    session: AsyncSession, grade: VeracrossItem
) -> list[VeracrossItem]:
    """Plausible assignments for this grade: same kid + same subject,
    due within [grade-60, grade+0]."""
    if not grade.due_or_date or not grade.subject:
        return []
    gd = _parse_loose_date(grade.due_or_date)
    if gd is None:
        return []
    floor = (gd - timedelta(days=60)).isoformat()
    ceil = (gd + timedelta(days=1)).isoformat()
    # Assignments use ISO; their due_or_date strings sort lexically,
    # so a string compare against ISO bounds works correctly.
    rows = (
        await session.execute(
            select(VeracrossItem)
            .where(VeracrossItem.kind == "assignment")
            .where(VeracrossItem.child_id == grade.child_id)
            .where(VeracrossItem.subject == grade.subject)
            .where(VeracrossItem.due_or_date >= floor)
            .where(VeracrossItem.due_or_date <= ceil)
        )
    ).scalars().all()
    return list(rows)


# ─── LLM tiebreaker ─────────────────────────────────────────────────────────

_LLM_PROMPT = """You are matching a graded item back to the assignment it grades.

Graded item:
  Title: {grade_title}
  Subject: {subject}
  Date graded: {grade_date}

Candidate assignments (each is a worksheet or test the kid was given):
{candidates_block}

Pick which candidate index (0..{n_minus_1}) best matches the graded item.
If none of them clearly match, reply with -1.

Reply ONLY with a JSON object in this exact format:
{{"choice": <integer>, "confidence": <0.0..1.0>, "reason": "<short>"}}
"""


async def _llm_pick(
    grade: VeracrossItem,
    candidates: list[tuple[VeracrossItem, float]],
) -> tuple[int, float, str] | None:
    """Returns (chosen_index, confidence, reason) or None on error."""
    from ..llm.client import LLMClient
    block = "\n".join(
        f"  [{i}] (due {a.due_or_date or '—'}) {a.title or '<untitled>'}"
        for i, (a, _s) in enumerate(candidates)
    )
    prompt = _LLM_PROMPT.format(
        grade_title=(grade.title or grade.title_en or "<untitled>"),
        subject=grade.subject or "—",
        grade_date=grade.due_or_date or "—",
        candidates_block=block,
        n_minus_1=len(candidates) - 1,
    )
    try:
        llm = LLMClient()
        resp = await llm.complete(
            purpose="grade_match",
            prompt=prompt,
            max_tokens=160,
            extra_cache_key=f"grade={grade.id}",
        )
    except Exception as e:
        log.warning("LLM grade-match failed: %s", e)
        return None
    text = resp.text.strip()
    # Try to extract a JSON object from the response.
    m = re.search(r"\{[^{}]*\}", text, re.S)
    if not m:
        log.warning("LLM grade-match: no JSON in %r", text[:200])
        return None
    try:
        obj = json.loads(m.group(0))
        return (int(obj["choice"]), float(obj.get("confidence", 0.5)),
                str(obj.get("reason", ""))[:200])
    except (ValueError, KeyError) as e:
        log.warning("LLM grade-match: parse fail %s in %r", e, text[:200])
        return None


# ─── top-level entry ────────────────────────────────────────────────────────

async def match_one_grade(
    session: AsyncSession,
    grade: VeracrossItem,
    *,
    use_llm_tiebreaker: bool = True,
    accept_threshold: float = 1.0,        # min absolute score to accept
    margin_threshold: float = 0.4,        # min top-vs-2nd margin for jaccard auto-accept
) -> dict[str, Any]:
    """Return {action, method, asg_id, confidence, reason} for one grade row.
    `action` ∈ {'linked', 'tied', 'no_candidates', 'all_weak', 'kept_existing'}.
    The DB row is updated in-place when action == 'linked'."""
    cands = await _candidates(session, grade)
    if not cands:
        return {"action": "no_candidates"}

    scored = sorted(((a, _score(grade, a)) for a in cands), key=lambda p: -p[1])
    top, top_score = scored[0]
    runner_score = scored[1][1] if len(scored) > 1 else 0.0
    margin = top_score - runner_score

    # If the existing link is already strong, leave it.
    if (
        grade.linked_assignment_id is not None
        and grade.match_confidence is not None
        and grade.match_confidence >= 1.2
    ):
        return {
            "action": "kept_existing",
            "asg_id": grade.linked_assignment_id,
            "confidence": grade.match_confidence,
            "method": grade.match_method or "jaccard",
        }

    # No candidate is strong enough.
    if top_score < accept_threshold:
        return {"action": "all_weak", "best": top.id, "score": top_score}

    # Clear winner — no LLM needed.
    if margin >= margin_threshold:
        grade.linked_assignment_id = top.id
        grade.match_confidence = round(top_score, 3)
        grade.match_method = "jaccard"
        return {
            "action": "linked",
            "asg_id": top.id,
            "confidence": top_score,
            "method": "jaccard",
        }

    # Ambiguous — ask the LLM (top 3 candidates).
    if not use_llm_tiebreaker:
        return {"action": "tied", "candidates": [a.id for a, _ in scored[:3]]}

    top3 = scored[:3]
    pick = await _llm_pick(grade, top3)
    if pick is None or pick[0] < 0 or pick[0] >= len(top3):
        return {"action": "tied", "candidates": [a.id for a, _ in top3]}
    chosen_idx, llm_conf, reason = pick
    chosen_asg = top3[chosen_idx][0]
    grade.linked_assignment_id = chosen_asg.id
    grade.match_confidence = round(top_score + 0.5 * llm_conf, 3)
    grade.match_method = "llm"
    return {
        "action": "linked",
        "asg_id": chosen_asg.id,
        "confidence": grade.match_confidence,
        "method": "llm",
        "reason": reason,
    }


async def match_unlinked_grades(
    session: AsyncSession,
    *,
    child_id: int | None = None,
    use_llm_tiebreaker: bool = True,
) -> dict[str, Any]:
    """Walk every grade row that doesn't yet have a strong link and try
    to assign one. Returns {linked, tied, no_candidates, all_weak,
    kept_existing} totals + a per-grade detail list."""
    q = select(VeracrossItem).where(VeracrossItem.kind == "grade")
    if child_id is not None:
        q = q.where(VeracrossItem.child_id == child_id)
    rows = (await session.execute(q)).scalars().all()

    counts = {"linked": 0, "tied": 0, "no_candidates": 0, "all_weak": 0,
              "kept_existing": 0}
    details: list[dict[str, Any]] = []
    for g in rows:
        r = await match_one_grade(
            session, g, use_llm_tiebreaker=use_llm_tiebreaker,
        )
        counts[r["action"]] = counts.get(r["action"], 0) + 1
        details.append({"grade_id": g.id, **r})
    await session.commit()
    return {"counts": counts, "details": details, "started_at": today_ist().isoformat()}
