"""Anomaly explanation per off-trend grade.

When a grade lands way off the kid's slope in that subject (e.g. 65 %
in Math after a 5-grade run averaging 95 %), the Today and Grades
pages now surface a Claude-generated *hypothesis* paragraph beside the
grade. The explanation reads the linked-assignment body, the recent
grades in the same subject, and any teacher comment from the same
window, and offers a falsifiable guess: time pressure vs concept gap
vs different test format vs an outlier the trend will absorb.

Detection (deterministic, no LLM):
  - subject must have ≥ 3 prior graded items
  - delta from the rolling mean must be ≥ 12 percentage points
  - or: pct must be ≥ 1.5 stddevs below the running mean

Explanation (Claude):
  - hand: this grade + assignment body + 4 prior grades in subject
    (with their bodies if linked) + any teacher comment within ±7 days
  - get: 2-3 sentence hypothesis that names ONE most-likely cause and
    cites the data ("follows the Apr-12 'rushed last 3 questions'
    note → time-pressure, not concept")

Cached on `veracross_items.llm_summary` for the grade row. Same column
the school-message and assignment-ask paths use, distinguished by the
row's `kind`. If we ever need three independent caches per row, that's
when we add dedicated columns.

Failure modes — return None:
  - too few prior grades to call it anomalous
  - LLM unreachable
  - LLM returns empty / off-topic output
"""
from __future__ import annotations

import json
import logging
from datetime import date, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..llm.client import LLMClient
from ..models import VeracrossItem
from .grade_match import _parse_loose_date
from .syllabus import normalize_subject


log = logging.getLogger(__name__)


# Minimum peers in subject before any anomaly can be called. With 1
# peer the central tendency is just the other grade, which is fragile.
MIN_PEER_SAMPLE = 2
# Pure-delta threshold (acts even at n=2 peers when the gap is huge).
# Uses median, not mean — a single outlier (e.g. one 0% no-attempt
# row in a stream of 90%s) won't shift the median, so non-outlier
# grades aren't flagged as echoes of the real outlier.
DELTA_THRESHOLD_PCT = 12.0
# Robust spread-based threshold using MAD (median absolute deviation).
# 3 × MAD ≈ 2σ for normally-distributed data; we use 3 here as the
# multiplier since it's more conservative than the old 1.5σ rule and
# MAD is naturally smaller than stddev. Requires ≥3 peers.
MAD_MULTIPLIER = 3.0
MAD_MIN_SAMPLE = 3


def _grade_pct(item: VeracrossItem) -> float | None:
    if not item.normalized_json:
        return None
    try:
        v = json.loads(item.normalized_json).get("grade_pct")
        return float(v) if v is not None else None
    except Exception:
        return None


def _median(values: list[float]) -> float:
    """Median — robust central tendency. For sorted [a, b, c, d]
    returns (b+c)/2; for [a, b, c, d, e] returns c."""
    if not values:
        return 0.0
    s = sorted(values)
    n = len(s)
    mid = n // 2
    return s[mid] if n % 2 else (s[mid - 1] + s[mid]) / 2


def _mad(values: list[float], median: float) -> float:
    """Median Absolute Deviation — robust spread. Equals 0 when ≥half
    of the values are at the median (e.g. five 90%s and one 0% gives
    MAD=0 from the median 90% — exactly the right behaviour: the 0%
    is the outlier, the 90%s aren't 'spread' from the 90% peak)."""
    if not values:
        return 0.0
    return _median([abs(v - median) for v in values])


def _stddev(values: list[float]) -> float:
    """Kept for backward compatibility with callers that read it
    elsewhere; no longer used by _is_anomalous."""
    n = len(values)
    if n < 2:
        return 0.0
    mean = sum(values) / n
    return (sum((v - mean) ** 2 for v in values) / (n - 1)) ** 0.5


async def _grades_in_subject(
    session: AsyncSession,
    child_id: int,
    subject_clean: str,
) -> list[tuple[date, float, VeracrossItem]]:
    rows = (
        await session.execute(
            select(VeracrossItem)
            .where(VeracrossItem.child_id == child_id)
            .where(VeracrossItem.kind == "grade")
        )
    ).scalars().all()
    out: list[tuple[date, float, VeracrossItem]] = []
    for r in rows:
        d = _parse_loose_date(r.due_or_date)
        pct = _grade_pct(r)
        s = normalize_subject(r.subject) or r.subject
        if d is None or pct is None or s != subject_clean:
            continue
        out.append((d, pct, r))
    out.sort(key=lambda t: t[0])
    return out


def _is_anomalous(
    pct: float, peer_pcts: list[float],
) -> tuple[bool, str]:
    """Returns (anomalous?, reason).

    Outlier-resistant detector — uses median + MAD (median absolute
    deviation) instead of mean + stddev. Critical for bimodal grade
    streams where a single 0% / no-attempt row would otherwise shift
    the mean enough to flag legitimate scores as "high outliers."

    Two firing rules:
      1. Pure delta — |Δ| ≥ 12 pts from the peer MEDIAN (≥2 peers).
      2. MAD-based — |Δ| ≥ 3 × MAD (only with ≥3 peers, MAD > 0).
    """
    if len(peer_pcts) < MIN_PEER_SAMPLE:
        return (False, f"need ≥ {MIN_PEER_SAMPLE} peer grades, have {len(peer_pcts)}")
    median = _median(peer_pcts)
    delta = pct - median
    direction = "below" if delta < 0 else "above"

    if abs(delta) >= DELTA_THRESHOLD_PCT:
        return (True, f"Δ {delta:+.1f} pts {direction} subject median {median:.1f}%")

    if len(peer_pcts) >= MAD_MIN_SAMPLE:
        mad = _mad(peer_pcts, median)
        if mad > 0 and abs(delta) / mad >= MAD_MULTIPLIER:
            return (
                True,
                f"Δ {delta:+.1f} pts {direction} subject median {median:.1f}% "
                f"(>{MAD_MULTIPLIER:.0f} MAD)",
            )

    return (False, f"Δ {delta:+.1f} pts within tolerance")


SYSTEM_PROMPT = """You are a thoughtful, careful explainer for a parent-cockpit app.

You will receive ONE grade that landed off the kid's recent trend in a
specific subject, plus context: the kid's prior grades in that subject
(with assignment bodies when linked), and any teacher-comment text
from a ±7-day window.

Your job: write a 2-3 sentence HYPOTHESIS for why this grade is off
trend. Pick ONE most-likely cause. Use the available data to ground
it; don't invent.

Allowed causes (if data supports them):
  - Time pressure / rushing / unfinished work (cite the comment if any)
  - Different test format (e.g. open-ended vs MCQ; longer; project-based)
  - Concept gap on a specific topic (cite which topic the body names)
  - Outlier the trend will likely absorb (when prior grades are tight
    and this is a single deviation)
  - First grade after a topic shift (when the assignment body names a
    new chapter / unit)

Forbidden:
  - Behavioural attribution ("the kid was lazy") — pedagogically harmful
  - Speculation about home life
  - Cheerleading ("don't worry!")
  - More than 3 sentences
  - Invented data

Format: 2-3 sentences, plain English, no headers, no bullets.

Examples of good output:

  "The 65 % follows a teacher note from Apr 12 that mentioned 'rushed
  the last 3 questions' — most likely time pressure, not a concept gap.
  Prior 3 math grades clustered 92-98 % so the trend is intact for now."

  "First long-form essay after weeks of MCQ-style assessments — a 75
  on the open-ended format suggests the writing-organization step,
  not the underlying knowledge. Worth checking the rubric to see
  which sub-skill scored lowest."

Output the paragraph and nothing else. No prefix, no JSON, no quotes."""


async def explain_grade_anomaly(
    session: AsyncSession,
    grade_id: int,
    *,
    force: bool = False,
) -> dict[str, Any]:
    """Detect + (if anomalous) explain. Returns:
       {grade_id, anomalous, reason, explanation, cached, llm_used}
       where `explanation` may be None if Claude is down or the grade
       isn't anomalous."""
    item = (
        await session.execute(
            select(VeracrossItem).where(VeracrossItem.id == grade_id)
        )
    ).scalar_one_or_none()
    if item is None or item.kind != "grade":
        raise ValueError(f"grade {grade_id} not found")

    subject = normalize_subject(item.subject) or item.subject
    pct = _grade_pct(item)
    if pct is None or not subject:
        return {
            "grade_id": grade_id,
            "anomalous": False,
            "reason": "no grade percentage",
            "explanation": None,
            "cached": False,
            "llm_used": False,
        }

    grades = await _grades_in_subject(session, item.child_id, subject)
    # Compare to the full subject distribution excluding this grade —
    # retrospective view is more useful for "why did THIS grade stick
    # out?" than the prospective "would this have surprised us at the
    # time?" view. The latter loses the first grade in every subject.
    peers = [(d, p, r) for d, p, r in grades if r.id != grade_id]
    peer_pcts = [p for _, p, _ in peers]

    anom, reason = _is_anomalous(pct, peer_pcts)
    if not anom:
        return {
            "grade_id": grade_id,
            "anomalous": False,
            "reason": reason,
            "explanation": None,
            "cached": False,
            "llm_used": False,
        }

    if not force and item.llm_summary:
        return {
            "grade_id": grade_id,
            "anomalous": True,
            "reason": reason,
            "explanation": item.llm_summary,
            "cached": True,
            "llm_used": False,
        }

    prior = peers  # back-compat alias for the rest of the function
    prior_pcts = peer_pcts

    # Build context pack for Claude.
    linked_assignment = None
    if item.linked_assignment_id:
        linked_assignment = (
            await session.execute(
                select(VeracrossItem).where(VeracrossItem.id == item.linked_assignment_id)
            )
        ).scalar_one_or_none()

    item_date = _parse_loose_date(item.due_or_date)
    teacher_comments: list[dict[str, Any]] = []
    if item_date is not None:
        comments = (
            await session.execute(
                select(VeracrossItem)
                .where(VeracrossItem.child_id == item.child_id)
                .where(VeracrossItem.kind == "comment")
            )
        ).scalars().all()
        for c in comments:
            cd = _parse_loose_date(c.due_or_date)
            if cd is None:
                continue
            if abs((cd - item_date).days) > 7:
                continue
            teacher_comments.append({
                "row_id": c.id,
                "date": cd.isoformat(),
                "text": c.title or c.title_en or "",
            })

    pack: dict[str, Any] = {
        "grade": {
            "row_id": item.id,
            "subject": subject,
            "title": item.title,
            "graded_date": item_date.isoformat() if item_date else None,
            "pct": pct,
            "score_text": (
                json.loads(item.normalized_json or "{}").get("score_text")
                if item.normalized_json else None
            ),
        },
        "subject_mean_pct": (
            sum(prior_pcts) / len(prior_pcts) if prior_pcts else None
        ),
        "subject_n_prior": len(prior_pcts),
        "anomaly_reason": reason,
        "linked_assignment": (
            {
                "row_id": linked_assignment.id,
                "title": linked_assignment.title,
                "body": linked_assignment.body,
                "type": (
                    json.loads(linked_assignment.normalized_json or "{}").get("type")
                    if linked_assignment.normalized_json else None
                ),
            }
            if linked_assignment else None
        ),
        "prior_grades": [
            {
                "row_id": r.id,
                "title": r.title,
                "graded_date": d.isoformat(),
                "pct": p,
            }
            for d, p, r in prior[-5:]  # last 5 prior
        ],
        "teacher_comments_in_window": teacher_comments,
    }

    client = LLMClient()
    if not client.enabled():
        return {
            "grade_id": grade_id,
            "anomalous": True,
            "reason": reason,
            "explanation": None,
            "cached": False,
            "llm_used": False,
        }

    prompt = (
        "DATA:\n```json\n"
        + json.dumps(pack, default=str, ensure_ascii=False, indent=2)
        + "\n```\n\nWrite the 2-3 sentence hypothesis."
    )
    try:
        resp = await client.complete(
            purpose="grade_anomaly_explanation",
            system=SYSTEM_PROMPT,
            prompt=prompt,
            max_tokens=240,
        )
    except Exception as e:
        log.warning("anomaly explanation failed for grade %s: %s", grade_id, e)
        return {
            "grade_id": grade_id,
            "anomalous": True,
            "reason": reason,
            "explanation": None,
            "cached": False,
            "llm_used": False,
        }

    text = (resp.text or "").strip()
    if text and text[0] in ('"', "'") and text[-1] in ('"', "'"):
        text = text[1:-1].strip()
    if len(text) > 600:
        text = text[:597].rstrip() + "…"
    if not text:
        return {
            "grade_id": grade_id,
            "anomalous": True,
            "reason": reason,
            "explanation": None,
            "cached": False,
            "llm_used": True,
        }

    item.llm_summary = text
    await session.commit()
    return {
        "grade_id": grade_id,
        "anomalous": True,
        "reason": reason,
        "explanation": text,
        "cached": False,
        "llm_used": True,
    }


async def detect_anomalies_for_child(
    session: AsyncSession, child_id: int,
) -> list[dict[str, Any]]:
    """Return one row per anomalous grade for the kid. Doesn't call
    Claude — pure detection. Used by the Today page banner / sync
    hook to know which grades warrant an explanation."""
    rows = (
        await session.execute(
            select(VeracrossItem)
            .where(VeracrossItem.child_id == child_id)
            .where(VeracrossItem.kind == "grade")
        )
    ).scalars().all()
    by_subj: dict[str, list[tuple[date, float, int]]] = {}
    for r in rows:
        d = _parse_loose_date(r.due_or_date)
        pct = _grade_pct(r)
        s = normalize_subject(r.subject) or r.subject
        if d is None or pct is None or not s:
            continue
        by_subj.setdefault(s, []).append((d, pct, r.id))

    out: list[dict[str, Any]] = []
    for subj, lst in by_subj.items():
        lst.sort(key=lambda t: t[0])
        for i, (d, pct, rid) in enumerate(lst):
            # Retrospective: compare to all peers in subject, not just
            # prior grades. See note on _is_anomalous use in
            # explain_grade_anomaly above.
            peers = [p for j, (_, p, _) in enumerate(lst) if j != i]
            anom, reason = _is_anomalous(pct, peers)
            if anom:
                out.append({
                    "grade_id": rid,
                    "subject": subj,
                    "graded_date": d.isoformat(),
                    "pct": pct,
                    "reason": reason,
                })
    return out
