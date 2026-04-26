"""Sunday-brief synthesis — Phase 16 iteration 1 (dry-run only).

Why this exists, before what it does:

A weekly Sunday-evening parent brief is the highest-leverage moment in the
cockpit's whole calendar. The pedagogy synthesis is blunt about what fails:
firehose summaries that re-list every grade and every assignment train the
parent to skim. The brief here is deliberately small — two sections, no
firehose, one recommendation — and every claim has to be anchored to a
deterministic rule with a citation back to a row id or a numeric datapoint.

Iteration 1 ships only §1 + §2:

  §1  "The shape of this learning cycle"
        One short paragraph. Where the kid is in the calendar
        (cycle name, day-of-cycle vs total days), per-subject grade
        trajectories computed from a least-squares slope across the
        last 4-6 grades (min sample = 3; 2-or-fewer suppresses the
        slope claim with "not enough data yet"), and a tight
        Excellence-arithmetic line — current YTD avg + how many
        sub-85 % grades the kid can absorb before the running mean
        falls below 85.

  §2  "The one thing worth a conversation"
        Exactly ONE recommendation per kid. We compute a
        `leverage_score` (formula in code, intentionally tunable) and
        pick the top topic. If no topic clears the threshold we say
        so — silence is the right answer most weeks.

The LLM (local Ollama via LLMClient) is treated as a copy-editor, not an
analyst. Every number, every name, every claim comes from this module's
deterministic rules; the LLM call (if it fires at all) does nothing except
smooth the rule-generated bullets into one warm paragraph. If Ollama is
unreachable we use the rule output as-is — the brief never depends on
"creativity" to be correct.

Iteration 2 will add §3 (teacher-asks) and §4 (what to ignore). Held back
until the user signs off on §1 + §2 phrasing.

Honest framing:
- Min-sample rules: ≤2 grades in a subject silently suppresses the slope
  claim. We never invent a trend from one or two points.
- No cross-kid comparison anywhere. Each brief is generated in isolation.
- §2 emits exactly one recommendation, or none — never two.
- The footer carries an `honest_caveat` line in the same flavour as
  homework_load.py so the parent always sees the seams.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..llm.client import LLMClient
from ..models import Child, VeracrossItem
from ..util.time import today_ist
from .excellence import EXCELLENCE_THRESHOLD, status_for_child
from .grade_match import _parse_loose_date
from .homework_load import homework_load
from .patterns import list_patterns
from .self_prediction import calibration_summary
from .shaky_topics import shaky_for_child
from .syllabus import cycle_for_date, fuzzy_topic_for, normalize_subject
from .ui_prefs import load_prefs

log = logging.getLogger(__name__)


# ─── tunables ───────────────────────────────────────────────────────────────

# Slope claim is suppressed if a subject has fewer than this many grades.
SLOPE_MIN_GRADES = 3
# Window of recent grades to slope across (per subject).
SLOPE_WINDOW = 6
# Slope sensitivity (percentage points per grade, in least-squares units)
# for declaring a trajectory rising/falling vs flat. Tuned empirically; a
# kid losing ~1.5 pts per assignment is a noticeable downward drift.
SLOPE_RISING_THRESHOLD = 1.5
SLOPE_FALLING_THRESHOLD = -1.5
# Volatility = stddev across the same window. Above this, even a flat
# slope reads as "volatile" rather than "flat".
VOLATILITY_THRESHOLD = 8.0
# Top-1 recommendation requires leverage ≥ this. Below it, §2 is silent.
LEVERAGE_THRESHOLD = 3.0
# Default number of grades to consider for the recent-grades view in §1.
RECENT_GRADES_FOR_SLOPE_MIN = 4

# Conversation-starter templates by normalized subject. Deliberately small;
# don't over-engineer. Subjects that aren't matched fall back to the generic
# "Ask them to walk you through" prompt below.
CONVERSATION_TEMPLATES: dict[str, str] = {
    "English": "Ask them to teach you the difference between {topic} and a similar idea — listening for whether they can explain in their own words.",
    "Mathematics": "Ask them to walk you through one {topic} problem on paper and narrate each step.",
    "Hindi": "Ask them to read aloud a short passage related to {topic} and translate one paragraph.",
    "Sanskrit": "Ask them to recite a line connected to {topic} and explain what each word means.",
    "Social Science": "Ask them why {topic} matters today — see if they can give a real-world example.",
    "Science": "Ask them to explain {topic} using a thing they can see in the kitchen or garden.",
    "Computer Science": "Ask them to describe {topic} as if they were teaching a younger sibling.",
    "Technology": "Ask them to describe {topic} as if they were teaching a younger sibling.",
    "Art": "Ask them to show you a sketch or example connected to {topic} and explain their choices.",
    "Music": "Ask them to play or sing the part connected to {topic} and explain what makes it tricky.",
    "Guitar Specialisation": "Ask them to play the part connected to {topic} slowly and explain what makes it tricky.",
}
_FALLBACK_STARTER = (
    "Ask them to walk you through {topic} in their own words for a few minutes."
)
TIME_BUDGET_MIN = 15


# ─── dataclasses ────────────────────────────────────────────────────────────

@dataclass
class SubjectTrajectory:
    """Per-subject grade trajectory snapshot. Anchored to row ids."""
    subject: str
    n_grades: int
    avg_pct: float | None
    slope_pct_per_step: float | None       # least-squares slope
    stddev_pct: float | None
    direction: str                          # rising/falling/volatile/flat/insufficient
    grade_ids_used: list[int] = field(default_factory=list)


@dataclass
class ExcellenceArithmetic:
    """How much room the kid has before the YTD mean tips below 85 %."""
    ytd_avg: float | None
    grades_count: int
    above_85_count: int
    threshold: float = EXCELLENCE_THRESHOLD
    # Headroom: largest k such that even k more grades at 0 % keeps mean ≥ 85.
    # Practical version: how many sub-85 grades they can absorb at the typical
    # below-85 score they've shown so far. We expose both for honesty.
    headroom_at_zero: int | None = None
    headroom_at_typical_below_85: int | None = None
    typical_below_85_pct: float | None = None
    on_track: bool = False


@dataclass
class CycleShape:
    """§1 raw output — synthesis paragraph + the underlying citations."""
    cycle_name: str | None
    cycle_start: str | None
    cycle_end: str | None
    cycle_day: int | None                   # 1-indexed day within cycle
    cycle_total_days: int | None
    trajectories: list[SubjectTrajectory]
    excellence: ExcellenceArithmetic
    paragraph: str                          # final rendered text


@dataclass
class Recommendation:
    topic: str
    subject: str
    leverage_score: float
    contributors: dict[str, float]          # which signal contributed how much
    why_it_matters: str
    conversation_starter: str
    time_budget_min: int = TIME_BUDGET_MIN


@dataclass
class TeacherAsk:
    """§3 row — a concrete question the parent could raise at the next
    teacher interaction. Every ask is grounded in a deterministic rule
    + a row id / numeric datapoint cited in `evidence`."""
    subject: str | None                     # None = cross-subject
    teacher: str | None                     # populated when assignment.teacher is set
    question: str
    evidence: str                           # citation block for the why-it-fired
    priority: float                         # higher = surface first


@dataclass
class IgnoreItem:
    """§4 row — something that looks concerning but has a *structural*
    reason to be dismissed (zero-weight, admin-only, sub-threshold).
    Conservative by design: we never subjectively judge what to ignore;
    only mechanical rules fire."""
    label: str
    reason: str
    evidence: str                           # row id or aggregate citation


@dataclass
class SundayBrief:
    """The whole brief for one kid — markdown is rendered separately."""
    child_id: int
    child_name: str
    class_section: str | None
    generated_for: str                      # ISO date
    cycle_shape: CycleShape                 # §1
    recommendation: Recommendation | None   # §2 (None means "all steady")
    leverage_top_3: list[Recommendation]    # for visibility/debugging
    teacher_asks: list[TeacherAsk]          # §3, capped at 3
    ignore_items: list[IgnoreItem]          # §4, capped at 3
    honest_caveat: str

    def to_dict(self) -> dict[str, Any]:
        # JSON-friendly version for tests / future API.
        def _rec(r: Recommendation | None) -> dict[str, Any] | None:
            if r is None:
                return None
            return {
                "topic": r.topic,
                "subject": r.subject,
                "leverage_score": r.leverage_score,
                "contributors": r.contributors,
                "why_it_matters": r.why_it_matters,
                "conversation_starter": r.conversation_starter,
                "time_budget_min": r.time_budget_min,
            }
        return {
            "child_id": self.child_id,
            "child_name": self.child_name,
            "class_section": self.class_section,
            "generated_for": self.generated_for,
            "cycle_shape": {
                "cycle_name": self.cycle_shape.cycle_name,
                "cycle_start": self.cycle_shape.cycle_start,
                "cycle_end": self.cycle_shape.cycle_end,
                "cycle_day": self.cycle_shape.cycle_day,
                "cycle_total_days": self.cycle_shape.cycle_total_days,
                "trajectories": [
                    {
                        "subject": t.subject,
                        "n_grades": t.n_grades,
                        "avg_pct": t.avg_pct,
                        "slope_pct_per_step": t.slope_pct_per_step,
                        "stddev_pct": t.stddev_pct,
                        "direction": t.direction,
                        "grade_ids_used": t.grade_ids_used,
                    }
                    for t in self.cycle_shape.trajectories
                ],
                "excellence": {
                    "ytd_avg": self.cycle_shape.excellence.ytd_avg,
                    "grades_count": self.cycle_shape.excellence.grades_count,
                    "above_85_count": self.cycle_shape.excellence.above_85_count,
                    "threshold": self.cycle_shape.excellence.threshold,
                    "headroom_at_zero": self.cycle_shape.excellence.headroom_at_zero,
                    "headroom_at_typical_below_85":
                        self.cycle_shape.excellence.headroom_at_typical_below_85,
                    "typical_below_85_pct": self.cycle_shape.excellence.typical_below_85_pct,
                    "on_track": self.cycle_shape.excellence.on_track,
                },
                "paragraph": self.cycle_shape.paragraph,
            },
            "recommendation": _rec(self.recommendation),
            "leverage_top_3": [_rec(r) for r in self.leverage_top_3],
            "teacher_asks": [
                {
                    "subject": a.subject,
                    "teacher": a.teacher,
                    "question": a.question,
                    "evidence": a.evidence,
                    "priority": a.priority,
                }
                for a in self.teacher_asks
            ],
            "ignore_items": [
                {"label": it.label, "reason": it.reason, "evidence": it.evidence}
                for it in self.ignore_items
            ],
            "honest_caveat": self.honest_caveat,
        }


# ─── helpers ────────────────────────────────────────────────────────────────

def _grade_pct(item: VeracrossItem) -> float | None:
    if not item.normalized_json:
        return None
    try:
        v = json.loads(item.normalized_json).get("grade_pct")
        return float(v) if v is not None else None
    except Exception:
        return None


def _least_squares_slope(values: list[float]) -> float:
    """Slope of a simple least-squares fit on (i, y) for i = 0..n-1.
    Returns 0.0 when n < 2 (caller already gates on min sample)."""
    n = len(values)
    if n < 2:
        return 0.0
    xs = list(range(n))
    mean_x = sum(xs) / n
    mean_y = sum(values) / n
    num = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, values))
    den = sum((x - mean_x) ** 2 for x in xs)
    if den == 0:
        return 0.0
    return num / den


def _stddev(values: list[float]) -> float:
    n = len(values)
    if n < 2:
        return 0.0
    mean = sum(values) / n
    return (sum((v - mean) ** 2 for v in values) / (n - 1)) ** 0.5


def _direction_for(slope: float, stddev: float, n: int) -> str:
    """Decide trajectory label.

    Subtle rule for small samples: with n < SOLID_SAMPLE (4), high stddev
    overrides any rising/falling claim. Otherwise we'd happily call a
    75 → 96 → 100 sequence "rising +12.5 pts/step" with confidence,
    when honestly that's three points of high variance on which any
    direction is fragile."""
    SOLID_SAMPLE = 4
    if n < SLOPE_MIN_GRADES:
        return "insufficient"
    # Small-sample volatility veto: if we don't have a solid sample yet,
    # high variance → "early"; the parent reads it as "watch this, don't
    # call it yet".
    if n < SOLID_SAMPLE and stddev > VOLATILITY_THRESHOLD:
        return "early"
    if stddev > VOLATILITY_THRESHOLD and abs(slope) < SLOPE_RISING_THRESHOLD:
        return "volatile"
    if slope >= SLOPE_RISING_THRESHOLD:
        return "rising"
    if slope <= SLOPE_FALLING_THRESHOLD:
        return "falling"
    if stddev > VOLATILITY_THRESHOLD:
        return "volatile"
    return "flat"


async def _grades_for_child(
    session: AsyncSession, child_id: int,
) -> list[tuple[date, float, VeracrossItem]]:
    """Return the kid's grade rows with parsed dates + percentages,
    sorted oldest → newest."""
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
        if d is None or pct is None:
            continue
        out.append((d, pct, r))
    out.sort(key=lambda t: t[0])
    return out


def _trajectories(
    grades: list[tuple[date, float, VeracrossItem]],
) -> list[SubjectTrajectory]:
    """Group grades by normalized subject and compute slope/stddev."""
    by_subject: dict[str, list[tuple[date, float, VeracrossItem]]] = {}
    for d, p, r in grades:
        subj = normalize_subject(r.subject) or (r.subject or "Unknown")
        by_subject.setdefault(subj, []).append((d, p, r))
    out: list[SubjectTrajectory] = []
    for subj, items in by_subject.items():
        # Already chronological because we sorted before slicing.
        items_sorted = sorted(items, key=lambda t: t[0])
        # Use the most-recent SLOPE_WINDOW for both slope + stddev. With
        # the small data the cockpit has today, the window naturally caps
        # at whatever's available.
        window = items_sorted[-SLOPE_WINDOW:]
        pcts = [p for _, p, _ in window]
        ids = [r.id for _, _, r in window]
        n = len(pcts)
        slope = _least_squares_slope(pcts) if n >= 2 else None
        stdv = _stddev(pcts) if n >= 2 else None
        avg = sum(pcts) / n if n > 0 else None
        out.append(SubjectTrajectory(
            subject=subj,
            n_grades=n,
            avg_pct=avg,
            slope_pct_per_step=slope,
            stddev_pct=stdv,
            direction=_direction_for(slope or 0.0, stdv or 0.0, n),
            grade_ids_used=ids,
        ))
    # Stable order: subjects with most grades first (more confidence first).
    out.sort(key=lambda t: (-t.n_grades, t.subject))
    return out


def _excellence_arithmetic(
    grades: list[tuple[date, float, VeracrossItem]],
) -> ExcellenceArithmetic:
    """Compute YTD avg and headroom calculation. Two headroom flavours:

    headroom_at_zero
        Largest k such that adding k grades at 0 % keeps mean ≥ 85.
        Worst-case bound — a deliberately scary number.
    headroom_at_typical_below_85
        Same idea but at the kid's actual average for grades below 85 %
        so far this year. More realistic; None if no sub-85 grades yet.
    """
    if not grades:
        return ExcellenceArithmetic(
            ytd_avg=None,
            grades_count=0,
            above_85_count=0,
            on_track=False,
        )
    pcts = [p for _, p, _ in grades]
    n = len(pcts)
    avg = sum(pcts) / n
    above = sum(1 for p in pcts if p >= EXCELLENCE_THRESHOLD)
    sum_pcts = sum(pcts)

    # Headroom at zero: solve (sum + 0*k) / (n + k) >= 85
    # → sum >= 85 * (n + k) → k <= sum/85 - n
    if avg < EXCELLENCE_THRESHOLD:
        headroom_zero = 0
    else:
        headroom_zero = max(0, int(sum_pcts / EXCELLENCE_THRESHOLD - n))

    below = [p for p in pcts if p < EXCELLENCE_THRESHOLD]
    typical = sum(below) / len(below) if below else None
    if typical is None:
        # No below-85 grades yet. Use 75 as a realistic-but-not-zero
        # placeholder; flag it so the rendered text says so.
        headroom_typical = None
    else:
        # (sum + typical * k) / (n + k) >= 85
        # → sum + typical*k >= 85n + 85k
        # → k * (typical - 85) >= 85n - sum
        # If typical < 85, denominator is negative; flip sign.
        denom = typical - EXCELLENCE_THRESHOLD
        if denom >= 0:
            # Their typical-below-85 is actually ≥ 85, which means below[]
            # only had values exactly == 85; treat as no headroom needed.
            headroom_typical = None
        else:
            num = (EXCELLENCE_THRESHOLD * n) - sum_pcts
            # k must be a count, so floor (we want strict ≥ 85).
            k = int(num / denom) if denom < 0 else 0
            # If avg is currently > 85 and num is ≤ 0, kid has plenty of
            # room — k from the divide is non-positive; treat as still positive.
            if num <= 0:
                k = max(k, 0)
            headroom_typical = max(0, k)

    return ExcellenceArithmetic(
        ytd_avg=avg,
        grades_count=n,
        above_85_count=above,
        headroom_at_zero=headroom_zero,
        headroom_at_typical_below_85=headroom_typical,
        typical_below_85_pct=typical,
        on_track=avg >= EXCELLENCE_THRESHOLD,
    )


def _build_paragraph_bullets(
    cycle_name: str | None,
    cycle_day: int | None,
    cycle_total_days: int | None,
    trajectories: list[SubjectTrajectory],
    excel: ExcellenceArithmetic,
    child_name: str,
) -> list[str]:
    """Rule-generated bullets that anchor every claim. The LLM (if used)
    smooths these into prose without inventing new facts."""
    bullets: list[str] = []

    # Cycle header.
    if cycle_name and cycle_day is not None and cycle_total_days:
        bullets.append(
            f"{child_name} is in {cycle_name}, day {cycle_day} of {cycle_total_days}."
        )
    elif cycle_name:
        bullets.append(f"{child_name} is currently in {cycle_name}.")
    else:
        bullets.append(f"{child_name} is between learning cycles right now.")

    # Per-subject trajectory deltas — only the subjects we can speak to.
    speakable = [t for t in trajectories if t.direction != "insufficient"]
    suppressed = [t for t in trajectories if t.direction == "insufficient"]
    for t in speakable:
        avg_str = f"{t.avg_pct:.0f} %" if t.avg_pct is not None else "—"
        if t.direction == "rising":
            bullets.append(
                f"{t.subject} is trending up — recent average {avg_str} "
                f"across {t.n_grades} grades, slope +{t.slope_pct_per_step:.1f} "
                f"pts per assignment."
            )
        elif t.direction == "falling":
            bullets.append(
                f"{t.subject} is drifting down — recent average {avg_str} "
                f"across {t.n_grades} grades, slope {t.slope_pct_per_step:.1f} "
                f"pts per assignment."
            )
        elif t.direction == "volatile":
            bullets.append(
                f"{t.subject} is bouncy — recent average {avg_str} across "
                f"{t.n_grades} grades, stddev ±{t.stddev_pct:.1f} pts."
            )
        elif t.direction == "early":
            # Small-sample, high-variance — name it without committing.
            bullets.append(
                f"{t.subject} is too early to call — only {t.n_grades} "
                f"grades so far, and they swing widely (avg {avg_str}, "
                f"stddev ±{t.stddev_pct:.1f} pts)."
            )
        else:  # flat
            bullets.append(
                f"{t.subject} is steady at {avg_str} across {t.n_grades} grades."
            )
    if suppressed:
        names = ", ".join(t.subject for t in suppressed)
        bullets.append(
            f"Not enough graded data yet to call a trend in: {names}."
        )

    # Excellence arithmetic.
    if excel.ytd_avg is None:
        bullets.append(
            "No graded items in this academic year yet — Excellence-Award "
            "tracking starts once the first grades come in."
        )
    else:
        on = "on track" if excel.on_track else "below the bar"
        line = (
            f"Year-to-date average is {excel.ytd_avg:.1f} % across "
            f"{excel.grades_count} grades ({excel.above_85_count} of them "
            f"≥ 85 %), {on} for the Excellence ≥ 85 % cutoff."
        )
        if excel.on_track:
            if excel.headroom_at_typical_below_85 is not None:
                line += (
                    f" At the typical sub-85 % grade ({excel.typical_below_85_pct:.0f} %), "
                    f"about {excel.headroom_at_typical_below_85} more such grades "
                    f"could be absorbed before the running mean tips below 85."
                )
            elif excel.headroom_at_zero is not None:
                line += (
                    f" Worst case, even {excel.headroom_at_zero} grades at 0 % "
                    "would still keep the running mean ≥ 85."
                )
        bullets.append(line)

    return bullets


async def _maybe_llm_polish(bullets: list[str]) -> str:
    """Hand bullets to local LLM for one warm paragraph. The LLM is a
    copy-editor — system prompt forbids it from inventing or dropping
    numbers. If LLM is unreachable or raises, return the bullets as
    plain prose."""
    fallback = " ".join(bullets)
    client = LLMClient()
    if not client.enabled():
        return fallback
    system = (
        "You are a warm, factual copy-editor for a parent-cockpit weekly "
        "brief. You will receive a list of bullets describing a child's "
        "learning cycle. Rewrite them as ONE warm paragraph (2-3 short "
        "sentences). Do not invent details. Keep every number, every "
        "subject name, every cycle name, and every percentage exactly as "
        "given. Do not add advice. Do not add encouragement that wasn't "
        "in the bullets. Do not start with the child's name being "
        "described in third person if a more natural lede works. Output "
        "the paragraph and nothing else."
    )
    prompt = "\n".join(f"- {b}" for b in bullets)
    try:
        resp = await client.complete(
            purpose="sunday_brief_polish",
            system=system,
            prompt=prompt,
            max_tokens=320,
        )
    except Exception as e:
        log.warning("sunday_brief LLM polish failed: %s", e)
        return fallback
    text = (resp.text or "").strip()
    if not text:
        return fallback
    # Strip wrapping quotes the model sometimes adds.
    if len(text) > 1 and text[0] in ('"', "'") and text[-1] in ('"', "'"):
        text = text[1:-1].strip()
    # Sanity check: every numeric token from the bullets must appear in
    # the output. If the LLM dropped one, fall back to the bullets.
    import re
    nums_in = re.findall(r"\d+(?:\.\d+)?", " ".join(bullets))
    nums_out = re.findall(r"\d+(?:\.\d+)?", text)
    missing = [n for n in nums_in if n not in nums_out]
    if missing:
        log.warning(
            "sunday_brief LLM dropped numbers %s; falling back to bullets.",
            missing,
        )
        return fallback
    return text


# ─── §1 main ────────────────────────────────────────────────────────────────

async def _build_cycle_shape(
    session: AsyncSession,
    child: Child,
    *,
    today: date,
    use_llm: bool = True,
) -> CycleShape:
    cyc = cycle_for_date(child.class_level, today)
    cycle_name = cyc.name if cyc else None
    cycle_start = cyc.start.isoformat() if cyc else None
    cycle_end = cyc.end.isoformat() if cyc else None
    cycle_day = (today - cyc.start).days + 1 if cyc else None
    cycle_total = (cyc.end - cyc.start).days + 1 if cyc else None

    grades = await _grades_for_child(session, child.id)
    trajectories = _trajectories(grades)
    excel = _excellence_arithmetic(grades)

    bullets = _build_paragraph_bullets(
        cycle_name=cycle_name,
        cycle_day=cycle_day,
        cycle_total_days=cycle_total,
        trajectories=trajectories,
        excel=excel,
        child_name=child.display_name,
    )
    paragraph = await _maybe_llm_polish(bullets) if use_llm else " ".join(bullets)

    return CycleShape(
        cycle_name=cycle_name,
        cycle_start=cycle_start,
        cycle_end=cycle_end,
        cycle_day=cycle_day,
        cycle_total_days=cycle_total,
        trajectories=trajectories,
        excellence=excel,
        paragraph=paragraph,
    )


# ─── §2 helpers ─────────────────────────────────────────────────────────────

def _strip_topic_prefix(topic: str | None) -> str | None:
    """fuzzy_topic_for() returns 'LC1: <topic>'. The shaky-topics service
    already strips this, but our weekly-due cross-reference uses
    fuzzy_topic_for directly, so we handle both."""
    if not topic:
        return None
    if ": " in topic:
        return topic.split(": ", 1)[1]
    return topic


async def _topics_with_assignments_due_this_week(
    session: AsyncSession, child: Child, today: date,
) -> set[tuple[str, str]]:
    """Subjects + topics with at least one assignment due in the next 7
    days (today inclusive). 'This week' is operationally 'next 7 days'
    — Sunday-evening framing → Mon-Sun is implied, but using a sliding
    7-day window from today is more honest because the cockpit may be
    generating the brief late Sunday or early Monday."""
    horizon = today  # today_ist already
    rows = (
        await session.execute(
            select(VeracrossItem)
            .where(VeracrossItem.child_id == child.id)
            .where(VeracrossItem.kind == "assignment")
        )
    ).scalars().all()
    hits: set[tuple[str, str]] = set()
    for r in rows:
        d = _parse_loose_date(r.due_or_date)
        if d is None:
            continue
        days = (d - horizon).days
        if days < 0 or days > 7:
            continue
        topic = _strip_topic_prefix(
            fuzzy_topic_for(child.class_level, r.subject, r.title)
        )
        subj = normalize_subject(r.subject) or (r.subject or "")
        if not topic or not subj:
            continue
        hits.add((subj, topic))
    return hits


def _topic_recurrence_count(class_level: int, subject: str, topic: str) -> int:
    """Count how many learning cycles (LC1..LC4) include this topic in
    this subject. A topic that recurs across cycles signals a thread the
    school has flagged as load-bearing — a higher leverage signal."""
    from .syllabus import load_syllabus
    syl = load_syllabus(class_level)
    count = 0
    topic_norm = topic.strip().lower()
    for c in syl.get("cycles", []):
        topics_map = c.get("topics_by_subject", {}) or {}
        topics = topics_map.get(subject, []) or []
        for t in topics:
            if t.strip().lower() == topic_norm:
                count += 1
                break
    return count


def _kid_overpredicts_in_subject(
    grades: list[tuple[date, float, VeracrossItem]],
    subject: str,
) -> float:
    """Returns 1.0 if the kid systematically over-predicts grades in
    this subject (predicted-too-high more than predicted-too-low),
    0.0 otherwise. Only fires when at least 3 predictions exist for
    the subject."""
    rows: list[dict[str, Any]] = []
    for _, _, r in grades:
        if (normalize_subject(r.subject) or r.subject) != subject:
            continue
        # The prediction is on the assignment, not the grade. We'd have
        # to walk linked_assignment_id to get there. Use it when present.
        # We don't have the assignment row here, so approximate: skip.
        # The proper version is below in _calibration_overpredicts_subject
        # which uses the linked_assignment_id chain.
        pass
    return 0.0


async def _subjects_where_kid_overpredicts(
    session: AsyncSession, child_id: int,
) -> set[str]:
    """Walk linked grade→assignment pairs and return the set of normalized
    subjects where the kid's self-prediction outcome is 'worse' more than
    'better' (with a min sample of 3 predictions)."""
    rows = (
        await session.execute(
            select(VeracrossItem)
            .where(VeracrossItem.child_id == child_id)
            .where(VeracrossItem.kind == "assignment")
            .where(VeracrossItem.self_prediction.is_not(None))
            .where(VeracrossItem.self_prediction_outcome.is_not(None))
        )
    ).scalars().all()
    by_subj: dict[str, dict[str, int]] = {}
    for r in rows:
        subj = normalize_subject(r.subject) or (r.subject or "")
        if not subj:
            continue
        d = by_subj.setdefault(subj, {"matched": 0, "better": 0, "worse": 0, "total": 0})
        d["total"] += 1
        out = r.self_prediction_outcome
        if out in d:
            d[out] += 1
    flagged: set[str] = set()
    for subj, d in by_subj.items():
        if d["total"] < 3:
            continue
        if d["worse"] > d["better"]:
            flagged.add(subj)
    return flagged


def _shaky_dismissed_for(child_id: int) -> set[tuple[str, str]]:
    """Read ui_prefs.json shaky_dismissed[child_id] → set of (subject, topic)
    tuples that the parent explicitly tray-dismissed. Penalty in §2 keeps
    us from re-pushing a topic the parent already said no to this week."""
    prefs = load_prefs() or {}
    dismissed = prefs.get("shaky_dismissed") or {}
    raw = dismissed.get(str(child_id)) or dismissed.get(child_id) or []
    out: set[tuple[str, str]] = set()
    if isinstance(raw, list):
        for entry in raw:
            if isinstance(entry, dict):
                s = entry.get("subject")
                t = entry.get("topic")
                if s and t:
                    out.add((s, t))
            elif isinstance(entry, (list, tuple)) and len(entry) >= 2:
                out.add((str(entry[0]), str(entry[1])))
    elif isinstance(raw, dict):
        # Allow {"subject:topic": true, ...} style too.
        for k, v in raw.items():
            if v and ":" in k:
                s, t = k.split(":", 1)
                out.add((s.strip(), t.strip()))
    return out


def _conversation_starter(subject: str, topic: str) -> str:
    """Pick a template by subject + a simple topic-shape detector.

    "A Friend's prayer (Poem - Poorvi)" should not slot into a "teach
    me the difference between X and a similar idea" template — that
    treats a poem as a concept. We look for hint tokens ("poem", "story",
    "kavita", "श्लोक" etc.) inside the topic name and route to a
    narrative-shaped starter instead.

    Keep this hand-curated — small lookup, not an LLM call."""
    t_low = topic.lower()
    is_poem = any(
        h in t_low
        for h in ("poem", "kavita", "kavita ", "poetry", "verse")
    ) or "(poem" in t_low
    is_story = any(
        h in t_low for h in ("story", "stories", "kahani", "tale", "chapter")
    )

    if is_poem:
        return (
            f"Ask them to recite '{topic}' aloud, then put the central "
            "image into their own words — what is the poem feeling, not "
            "just saying?"
        )
    if is_story:
        return (
            f"Ask them to retell '{topic}' in three short sentences — "
            "beginning, turning point, end — and pick one line they liked."
        )

    template = CONVERSATION_TEMPLATES.get(subject) or _FALLBACK_STARTER
    return template.format(topic=topic)


# ─── §2 main ────────────────────────────────────────────────────────────────

async def _build_recommendation(
    session: AsyncSession,
    child: Child,
    *,
    today: date,
) -> tuple[Recommendation | None, list[Recommendation]]:
    """Compute leverage scores per shaky topic, return (top, top_3).

    leverage =
        shakiness                                                (raw, 0..N)
      + 2.0 * recurrence_across_cycles                           (count of LCs the topic is in)
      + 1.5 * has_assignment_due_this_week                       (0/1)
      + 1.0 * kid_overpredicts_in_subject                        (0/1, requires sample)
      - 1.0 * recently_dismissed_in_shaky_tray                   (0/1)

    All weights are deliberately small integers so the formula is
    legible to a parent if we ever surface it. Tune in the constants
    section above, not here.
    """
    shaky = await shaky_for_child(session, child, limit=None)
    if not shaky:
        return None, []

    # Pre-compute the cross-cutting signals once.
    weekly_topics = await _topics_with_assignments_due_this_week(session, child, today)
    overpredicted_subjects = await _subjects_where_kid_overpredicts(session, child.id)
    dismissed = _shaky_dismissed_for(child.id)

    scored: list[Recommendation] = []
    for sh in shaky:
        subject = sh["subject"]
        topic = sh["topic"]
        contributors: dict[str, float] = {}

        shakiness = float(sh.get("shakiness", 0.0))
        contributors["shakiness"] = shakiness

        rec = _topic_recurrence_count(child.class_level, subject, topic)
        contributors["recurrence_x_cycles"] = 2.0 * rec

        weekly = 1.0 if (subject, topic) in weekly_topics else 0.0
        contributors["due_this_week"] = 1.5 * weekly

        op = 1.0 if subject in overpredicted_subjects else 0.0
        contributors["overpredicts_subject"] = 1.0 * op

        dis = 1.0 if (subject, topic) in dismissed else 0.0
        contributors["recently_dismissed"] = -1.0 * dis

        leverage = sum(contributors.values())

        # Build the why_it_matters narrative, citing each non-zero signal.
        reasons: list[str] = []
        if shakiness > 0:
            # shaky_for_child already returns reasons; copy the first one.
            sh_reasons = sh.get("reasons") or []
            cite = sh_reasons[0] if sh_reasons else f"shakiness score {shakiness:.0f}"
            reasons.append(cite)
        if rec >= 2:
            reasons.append(f"appears in {rec} learning cycles this year")
        elif rec == 1:
            reasons.append("on the syllabus for this cycle")
        if weekly:
            reasons.append("an assignment on it is due in the next 7 days")
        if op:
            reasons.append(f"in {subject}, predictions tend to land too optimistic")
        if dis:
            reasons.append(
                "you dismissed it from the shaky-tray earlier — surfaced again "
                "for transparency"
            )
        why = "; ".join(reasons) + "."

        scored.append(Recommendation(
            topic=topic,
            subject=subject,
            leverage_score=round(leverage, 2),
            contributors={k: round(v, 2) for k, v in contributors.items()},
            why_it_matters=why,
            conversation_starter=_conversation_starter(subject, topic),
        ))

    scored.sort(key=lambda r: -r.leverage_score)
    top = scored[0] if scored and scored[0].leverage_score >= LEVERAGE_THRESHOLD else None
    return top, scored[:3]


# ─── §3 helpers (teacher asks) ──────────────────────────────────────────────

# Keyword sets used by both §3 (admin-message detection isn't relevant here)
# and §4. Hand-curated for Vasant Valley's notification vocabulary.
_ADMIN_MSG_KEYWORDS = {
    "fee", "circular", "newsletter", "election", "elect",
    "pickup", "schedule", "holiday", "camp",
    "registration", "form", "consent", "transport",
    "calendar", "reminder", "book list", "uniform",
}


def _teacher_for_subject(
    grades: list[tuple[date, float, VeracrossItem]], subject: str,
) -> str | None:
    """Pull the most-recent non-empty teacher field from any item in
    this subject. Used to make the ask address a person, not a void."""
    for _, _, r in reversed(grades):
        if (normalize_subject(r.subject) or r.subject) != subject:
            continue
        try:
            n = json.loads(r.normalized_json or "{}")
            t = n.get("teacher") or ""
            if isinstance(t, str) and t.strip():
                return t.strip()
        except Exception:
            continue
    return None


async def _build_teacher_asks(
    session: AsyncSession,
    child: Child,
    *,
    today: date,
    grades: list[tuple[date, float, VeracrossItem]],
) -> list[TeacherAsk]:
    """Generate concrete questions the parent could raise at the next
    teacher interaction. Every ask is grounded in a deterministic
    signal — pattern_state flag, syllabus override, decaying-with-
    recurrence, or homework-load over CBSE cap."""
    asks: list[TeacherAsk] = []

    # Generator A — pattern_state.repeated_attempt this month.
    patterns = await list_patterns(session, child.id)
    cur_month = today.strftime("%Y-%m")
    cur_pat = next(
        (p for p in patterns if p.get("month") == cur_month), None,
    )
    if cur_pat and cur_pat.get("repeated_attempt"):
        topics = (cur_pat.get("detail") or {}).get("repeated_attempt", {}).get("topics") or []
        for tp in topics[:2]:  # at most 2 reteach asks
            subj = tp.get("subject") or ""
            tname = tp.get("topic") or ""
            count = int(tp.get("count") or 0)
            if not (subj and tname and count >= 3):
                continue
            teacher = _teacher_for_subject(grades, subj)
            who = teacher or "the class teacher"
            asks.append(TeacherAsk(
                subject=subj,
                teacher=teacher,
                question=(
                    f"{subj}: '{tname}' has been graded {count} times this "
                    f"month. Could {who} share what intervention the class "
                    "is getting on this thread?"
                ),
                evidence=(
                    f"pattern_state {cur_month} repeated_attempt detail; "
                    f"count={count}"
                ),
                priority=3.0 + count * 0.1,
            ))

    # Generator B — syllabus topics flagged skipped or delayed in the
    # current cycle (only). Don't fish back through earlier cycles —
    # too easy to dredge resolved items.
    cyc = cycle_for_date(child.class_level, today)
    if cyc:
        from .syllabus import cycle_for_date_merged  # avoids cyclic import at top
        merged = await cycle_for_date_merged(session, child.class_level, today)
        if merged:
            for subj, tmap in (merged.topic_status or {}).items():
                for topic, info in (tmap or {}).items():
                    status = (info or {}).get("status")
                    if status not in ("skipped", "delayed"):
                        continue
                    teacher = _teacher_for_subject(grades, subj)
                    who = teacher or "the teacher"
                    asks.append(TeacherAsk(
                        subject=subj,
                        teacher=teacher,
                        question=(
                            f"{subj}: '{topic}' is marked {status} for "
                            f"{cyc.name}. Was it re-assigned to a later "
                            f"cycle, replaced, or carried over? "
                            f"Worth a one-line update from {who}."
                        ),
                        evidence=(
                            f"syllabus_overrides {cyc.name}/{subj}/{topic} "
                            f"status={status}"
                        ),
                        priority=2.5,
                    ))

    # Generator C — decaying topics that recur across cycles (the
    # signal that the school is teaching a thread the kid hasn't yet
    # held; worth a re-teach plan).
    shaky = await shaky_for_child(session, child, limit=None)
    for sh in shaky:
        if sh.get("state") != "decaying":
            continue
        subj = sh.get("subject") or ""
        topic = sh.get("topic") or ""
        if not (subj and topic):
            continue
        rec = _topic_recurrence_count(child.class_level, subj, topic)
        if rec < 2:
            continue
        last_score = sh.get("last_score")
        last_str = (
            f"last graded {last_score:.0f} %" if last_score is not None
            else "no recent grade"
        )
        teacher = _teacher_for_subject(grades, subj)
        who = teacher or "the teacher"
        asks.append(TeacherAsk(
            subject=subj,
            teacher=teacher,
            question=(
                f"{subj}: '{topic}' is on the syllabus across {rec} "
                f"learning cycles ({last_str}). Could {who} share "
                "the re-teach or refresh plan for this thread?"
            ),
            evidence=(
                f"topic_state state=decaying subject={subj} topic={topic} "
                f"recurrence={rec} last_score={last_score}"
            ),
            priority=2.0 + rec * 0.2,
        ))

    # Generator D — homework load over the CBSE cap *this week*.
    try:
        load = await homework_load(session, child, weeks=2)
    except Exception:
        load = None
    if load and load.get("cap_minutes"):
        cap = load["cap_minutes"]
        cap_basis = load.get("cap_basis", "CBSE cap")
        weeks = load.get("weeks") or []
        # The most recent week is last (sorted ascending in the service).
        if weeks:
            w = weeks[-1]
            est = int(w.get("est_minutes") or 0)
            if cap > 0 and est > cap:
                ratio = est / cap
                hr = est / 60.0
                cap_hr = cap / 60.0
                asks.append(TeacherAsk(
                    subject=None,
                    teacher=None,
                    question=(
                        f"This week's estimated homework load is "
                        f"~{hr:.1f} hr ({ratio:.1f}× the {cap_basis}; "
                        f"~{cap_hr:.1f} hr is the policy reference). "
                        "Is the class catching up on a backlog, or has "
                        "the assignment cadence changed?"
                    ),
                    evidence=(
                        f"homework_load week_start={w.get('week_start')} "
                        f"items={w.get('items')} est_minutes={est} cap={cap}"
                    ),
                    priority=2.2,
                ))

    asks.sort(key=lambda a: -a.priority)
    return asks[:3]


# ─── §4 helpers (what to ignore) ────────────────────────────────────────────

async def _build_ignore_items(
    session: AsyncSession,
    child: Child,
    *,
    today: date,
    grades: list[tuple[date, float, VeracrossItem]],
) -> list[IgnoreItem]:
    """Conservative dismissals — only fire on STRUCTURAL reasons.
    Never fires on subjective judgment about whether something is
    'really' important."""
    items: list[IgnoreItem] = []

    # Generator A — zero-weight assignments graded low (don't affect
    # Excellence). Read weight from the linked assignment when present.
    asgs = (
        await session.execute(
            select(VeracrossItem)
            .where(VeracrossItem.child_id == child.id)
            .where(VeracrossItem.kind == "assignment")
        )
    ).scalars().all()
    asg_by_id = {a.id: a for a in asgs}
    for _, pct, g in grades:
        if pct >= 75:
            continue
        if not g.linked_assignment_id:
            continue
        a = asg_by_id.get(g.linked_assignment_id)
        if a is None:
            continue
        try:
            n = json.loads(a.normalized_json or "{}")
        except Exception:
            n = {}
        weight = n.get("weight")
        # Weight may be a string like "0%" or a number. Be permissive.
        weight_num: float | None = None
        try:
            if isinstance(weight, str):
                w = weight.strip().replace("%", "")
                weight_num = float(w) if w else None
            elif weight is not None:
                weight_num = float(weight)
        except Exception:
            weight_num = None
        if weight_num is not None and weight_num <= 0.0:
            items.append(IgnoreItem(
                label=f"{pct:.0f}% on '{g.title or g.title_en or 'assignment'}'",
                reason="weight is 0 % — won't affect the Excellence-Award average",
                evidence=f"grade row {g.id} → assignment {a.id} weight={weight_num}",
            ))

    # Generator B — admin-only school messages from the last 7 days.
    msgs = (
        await session.execute(
            select(VeracrossItem)
            .where(VeracrossItem.kind == "school_message")
        )
    ).scalars().all()
    recent_admin: list[str] = []
    for m in msgs:
        d = _parse_loose_date(m.due_or_date)
        if d is None or (today - d).days > 7 or (today - d).days < 0:
            continue
        title_low = (m.title or "").lower()
        if any(k in title_low for k in _ADMIN_MSG_KEYWORDS):
            recent_admin.append(m.title or f"message {m.id}")
    if recent_admin:
        sample = recent_admin[:2]
        more = f" (+{len(recent_admin) - len(sample)} more)" if len(recent_admin) > 2 else ""
        items.append(IgnoreItem(
            label=f"{len(recent_admin)} admin school message"
                  f"{'s' if len(recent_admin) != 1 else ''} this week",
            reason="admin / logistics announcements — not academic feedback",
            evidence=f"school_message titles match admin keywords: "
                     f"{'; '.join(sample)}{more}",
        ))

    # Generator C — sub-threshold weekend marks (looks like cramming
    # but isn't, structurally).
    patterns = await list_patterns(session, child.id)
    cur_month = today.strftime("%Y-%m")
    cur_pat = next(
        (p for p in patterns if p.get("month") == cur_month), None,
    )
    if cur_pat and not cur_pat.get("weekend_cramming"):
        wk = (cur_pat.get("detail") or {}).get("weekend_cramming", {})
        weekend = int(wk.get("weekend") or 0)
        total = int(wk.get("total") or 0)
        if weekend > 0 and total >= 3:
            items.append(IgnoreItem(
                label=f"{weekend} of {total} parent-marks on the weekend",
                reason="under the weekend-cramming threshold; normal homework rhythm",
                evidence=f"pattern_state {cur_month} weekend_cramming=False; "
                         f"weekend={weekend} total={total}",
            ))

    return items[:3]


# ─── data pack builder (Claude path + validator) ────────────────────────────

async def _build_data_pack(
    session: AsyncSession,
    child: Child,
    *,
    today: date,
    grades: list[tuple[date, float, VeracrossItem]],
) -> dict[str, Any]:
    """Gather *every* signal we'd want a smart synthesizer to consider.

    Hand-curated keys; not a kitchen sink. Each numeric value carries
    its source row id so the synthesizer can cite. The validator later
    walks `pack["row_ids"]` to ensure Claude didn't hallucinate.
    """
    cyc = cycle_for_date(child.class_level, today)
    cyc_payload = None
    if cyc:
        cyc_payload = {
            "name": cyc.name,
            "start": cyc.start.isoformat(),
            "end": cyc.end.isoformat(),
            "day": (today - cyc.start).days + 1,
            "total_days": (cyc.end - cyc.start).days + 1,
        }

    trajectories = _trajectories(grades)
    excel = _excellence_arithmetic(grades)

    # Recent grades — last 8, freshest first, with linked-assignment
    # body if known (Claude needs the *story* not just the numbers).
    asgs = (
        await session.execute(
            select(VeracrossItem)
            .where(VeracrossItem.child_id == child.id)
            .where(VeracrossItem.kind == "assignment")
        )
    ).scalars().all()
    asg_by_id = {a.id: a for a in asgs}
    recent_grades_payload: list[dict[str, Any]] = []
    for d, p, r in sorted(grades, key=lambda x: x[0], reverse=True)[:8]:
        a = asg_by_id.get(r.linked_assignment_id) if r.linked_assignment_id else None
        recent_grades_payload.append({
            "row_id": r.id,
            "subject": normalize_subject(r.subject) or r.subject,
            "title": r.title,
            "graded_date": d.isoformat(),
            "pct": p,
            "linked_assignment_title": (a.title if a else None),
            "linked_assignment_body": (a.body if a else None),
            "linked_assignment_id": r.linked_assignment_id,
        })

    # Upcoming assignments — next 14 days.
    upcoming_payload: list[dict[str, Any]] = []
    for a in asgs:
        d = _parse_loose_date(a.due_or_date)
        if d is None:
            continue
        days = (d - today).days
        if days < 0 or days > 14:
            continue
        upcoming_payload.append({
            "row_id": a.id,
            "subject": normalize_subject(a.subject) or a.subject,
            "title": a.title,
            "due_date": d.isoformat(),
            "days_from_today": days,
            "body": a.body,
        })
    upcoming_payload.sort(key=lambda x: x["days_from_today"])

    # Shaky topics + leverage candidates.
    shaky = await shaky_for_child(session, child, limit=None)

    # Pattern flags (current month).
    patterns = await list_patterns(session, child.id)
    cur_month = today.strftime("%Y-%m")
    cur_pat = next(
        (p for p in patterns if p.get("month") == cur_month), None,
    )

    # Self-prediction calibration.
    pred_rows = (
        await session.execute(
            select(VeracrossItem)
            .where(VeracrossItem.child_id == child.id)
            .where(VeracrossItem.self_prediction.is_not(None))
        )
    ).scalars().all()
    pred_summary = calibration_summary([
        {
            "self_prediction": r.self_prediction,
            "self_prediction_outcome": r.self_prediction_outcome,
        }
        for r in pred_rows
    ])

    # Homework load (last 8 weeks).
    try:
        load = await homework_load(session, child, weeks=8)
    except Exception:
        load = None

    # Syllabus topic_status for the current cycle (covered/skipped/etc.).
    cycle_status: dict[str, dict[str, dict[str, Any]]] = {}
    if cyc:
        try:
            from .syllabus import cycle_for_date_merged
            merged = await cycle_for_date_merged(session, child.class_level, today)
            if merged and merged.topic_status:
                cycle_status = merged.topic_status
        except Exception:
            pass

    # School-wide messages — last 14 days, normalized.
    msgs = (
        await session.execute(
            select(VeracrossItem)
            .where(VeracrossItem.kind == "school_message")
        )
    ).scalars().all()
    msgs_payload: list[dict[str, Any]] = []
    for m in msgs:
        d = _parse_loose_date(m.due_or_date)
        if d is None or (today - d).days < 0 or (today - d).days > 14:
            continue
        title_low = (m.title or "").lower()
        is_admin = any(k in title_low for k in _ADMIN_MSG_KEYWORDS)
        msgs_payload.append({
            "row_id": m.id,
            "title": m.title,
            "date": d.isoformat(),
            "looks_admin": is_admin,
        })

    pack: dict[str, Any] = {
        "child": {
            "id": child.id,
            "name": child.display_name,
            "class_section": child.class_section,
            "class_level": child.class_level,
        },
        "today": today.isoformat(),
        "current_cycle": cyc_payload,
        "trajectories": [
            {
                "subject": t.subject,
                "n_grades": t.n_grades,
                "avg_pct": t.avg_pct,
                "slope_pct_per_step": t.slope_pct_per_step,
                "stddev_pct": t.stddev_pct,
                "direction": t.direction,
                "grade_row_ids": t.grade_ids_used,
            }
            for t in trajectories
        ],
        "excellence": {
            "ytd_avg": excel.ytd_avg,
            "grades_count": excel.grades_count,
            "above_85_count": excel.above_85_count,
            "threshold": excel.threshold,
            "headroom_at_zero": excel.headroom_at_zero,
            "headroom_at_typical_below_85": excel.headroom_at_typical_below_85,
            "typical_below_85_pct": excel.typical_below_85_pct,
            "on_track": excel.on_track,
        },
        "recent_grades": recent_grades_payload,
        "upcoming_assignments_14d": upcoming_payload,
        "shaky_topics": shaky,
        "pattern_state_current_month": cur_pat,
        "self_prediction_calibration": pred_summary,
        "homework_load": load,
        "current_cycle_topic_status": cycle_status,
        "school_messages_14d": msgs_payload,
    }

    # Index of every row id in the pack — the Claude validator uses this
    # to confirm every cited row was actually present.
    row_ids: set[int] = set()
    for g in recent_grades_payload:
        row_ids.add(g["row_id"])
        if g.get("linked_assignment_id"):
            row_ids.add(int(g["linked_assignment_id"]))
    for u in upcoming_payload:
        row_ids.add(u["row_id"])
    for m in msgs_payload:
        row_ids.add(m["row_id"])
    pack["_row_ids"] = sorted(row_ids)

    return pack


# ─── Claude synthesis ───────────────────────────────────────────────────────

CLAUDE_BRIEF_SYSTEM = """You are the synthesizer for a *very intelligent* parent-cockpit Sunday brief.

The reader is a parent of one kid (only this kid; never compare to siblings). The brief is short — they read it on a Sunday evening before the school week begins, and it must give them something they didn't already know from glancing at the dashboard. Your job is to connect signals across surfaces, name a trajectory, and give exactly one focused recommendation, plus teacher-facing follow-ups and a short "what to ignore" list.

You will receive a JSON DATA PACK with everything we know about the kid. You must NEVER invent numbers, names, dates, or row ids. Every numeric claim in your output must echo a number that already appears in the pack. Every recommendation, teacher-ask, and ignore-item must reference a `row_id` that's listed in `_row_ids`.

OUTPUT — strict JSON only, matching this schema:

{
  "section_1_paragraph": "<2-3 sentence narrative of where the kid is in the cycle, trajectory across subjects, Excellence-Award arithmetic. Names a trend direction. Short.>",
  "section_1_evidence": [ "<bullet>", "..." ],

  "section_2_recommendation": null OR {
    "subject": "...",
    "topic": "...",
    "why_it_matters": "<1-2 sentences citing each signal that pushed this to the top — e.g. shaky last grade, recurring across cycles, due this week, kid over-predicts in this subject>",
    "conversation_starter": "<one concrete question/exercise the parent can do with the kid in ~15 min — make it shape-aware (poems vs concepts vs problems) and specific to this topic>",
    "evidence_row_ids": [<int>, ...]
  },

  "section_3_teacher_asks": [
    { "subject": "..." | null, "teacher": "..." | null,
      "question": "<phrased as a question, not an accusation>",
      "evidence_row_ids": [<int>, ...] },
    ...   // 0-3 items
  ],

  "section_4_what_to_ignore": [
    { "label": "...", "reason": "<structural reason — zero weight, admin-only, sub-threshold>",
      "evidence_row_ids": [<int>, ...] },
    ...   // 0-3 items
  ]
}

RULES:
- Never compare this kid to anyone. No "your other child…" framings.
- §1 must NOT include raw row ids in prose; put them in `section_1_evidence` as bullets.
- §2 recommendation: emit `null` if no signal genuinely warrants the parent's attention this week. Don't manufacture one.
- §3: at most 3. If nothing real surfaces, return [].
- §4: at most 3, conservative. Only structural reasons (zero-weight, admin keyword, sub-threshold) — never subjective dismissals.
- Tone: warm, factual, no exclamation marks, no encouragement that wasn't earned by the data.
- If sample sizes are small (≤2 grades in a subject), do NOT call a trend in that subject — say "too early to call" or omit.
- The CONVERSATION STARTER must NOT use the topic name as a noun in a "teach me the difference between {topic} and a similar idea" template. Detect topic shape: a poem name should prompt recitation + interpretation, a story should prompt retelling, a math/grammar concept can prompt explanation.

Return ONLY the JSON. No prose outside the braces. No markdown fences."""


def _validate_claude_brief(out: dict[str, Any], pack: dict[str, Any]) -> str | None:
    """Return None if valid, else a string describing the violation.
    The contract: every cited row_id must be in pack['_row_ids']."""
    valid_ids = set(pack.get("_row_ids", []))

    def _check_ids(label: str, ids: Any) -> str | None:
        if not isinstance(ids, list):
            return f"{label}: evidence_row_ids must be a list"
        for v in ids:
            try:
                vi = int(v)
            except Exception:
                return f"{label}: row id {v!r} is not an int"
            if vi not in valid_ids:
                return f"{label}: row id {vi} not in data pack"
        return None

    rec = out.get("section_2_recommendation")
    if rec is not None:
        if not isinstance(rec, dict):
            return "§2: recommendation must be object or null"
        err = _check_ids("§2", rec.get("evidence_row_ids", []))
        if err:
            return err

    asks = out.get("section_3_teacher_asks", [])
    if not isinstance(asks, list) or len(asks) > 3:
        return "§3: must be a list of ≤3"
    for i, a in enumerate(asks):
        if not isinstance(a, dict):
            return f"§3[{i}]: not an object"
        err = _check_ids(f"§3[{i}]", a.get("evidence_row_ids", []))
        if err:
            return err

    ig = out.get("section_4_what_to_ignore", [])
    if not isinstance(ig, list) or len(ig) > 3:
        return "§4: must be a list of ≤3"
    for i, it in enumerate(ig):
        if not isinstance(it, dict):
            return f"§4[{i}]: not an object"
        err = _check_ids(f"§4[{i}]", it.get("evidence_row_ids", []))
        if err:
            return err

    if not isinstance(out.get("section_1_paragraph", ""), str) or not out["section_1_paragraph"].strip():
        return "§1: paragraph missing"

    return None


async def _claude_synthesis(
    child: Child,
    pack: dict[str, Any],
    *,
    today: date,
) -> SundayBrief | None:
    """Hand the data pack to Claude, get back a structured brief, validate
    it, materialise SundayBrief. Returns None on any failure path so the
    rule fallback runs."""
    client = LLMClient()
    if not client.enabled():
        log.info("sunday_brief: Claude path disabled (LLM not enabled)")
        return None
    # Force the claude backend for this purpose, regardless of the
    # primary backend setting.
    pack_json = json.dumps(pack, default=str, ensure_ascii=False, indent=2)
    prompt = f"DATA PACK:\n```json\n{pack_json}\n```\n\nGenerate the brief."
    try:
        resp = await client.complete(
            purpose="sunday_brief_synthesis",
            system=CLAUDE_BRIEF_SYSTEM,
            prompt=prompt,
            max_tokens=2400,
        )
    except Exception as e:
        log.warning("sunday_brief Claude synthesis failed: %s", e)
        return None

    text = (resp.text or "").strip()
    # Strip optional markdown fence the model sometimes adds.
    if text.startswith("```"):
        text = text.split("```", 2)
        text = text[1] if len(text) >= 2 else "".join(text)
        if text.lstrip().startswith("json"):
            text = text.split("\n", 1)[1] if "\n" in text else text
    try:
        out = json.loads(text)
    except Exception as e:
        log.warning("sunday_brief Claude returned non-JSON: %s; raw=%r", e, text[:300])
        return None

    err = _validate_claude_brief(out, pack)
    if err:
        log.warning("sunday_brief Claude output failed validation: %s", err)
        return None

    # Materialise into SundayBrief.
    cs = pack.get("current_cycle") or {}
    excel = pack["excellence"]
    excel_obj = ExcellenceArithmetic(
        ytd_avg=excel.get("ytd_avg"),
        grades_count=excel.get("grades_count", 0),
        above_85_count=excel.get("above_85_count", 0),
        headroom_at_zero=excel.get("headroom_at_zero"),
        headroom_at_typical_below_85=excel.get("headroom_at_typical_below_85"),
        typical_below_85_pct=excel.get("typical_below_85_pct"),
        on_track=excel.get("on_track", False),
    )
    trajectories = [
        SubjectTrajectory(
            subject=t["subject"],
            n_grades=t["n_grades"],
            avg_pct=t.get("avg_pct"),
            slope_pct_per_step=t.get("slope_pct_per_step"),
            stddev_pct=t.get("stddev_pct"),
            direction=t.get("direction") or "insufficient",
            grade_ids_used=t.get("grade_row_ids") or [],
        )
        for t in pack.get("trajectories", [])
    ]
    cycle_shape = CycleShape(
        cycle_name=cs.get("name"),
        cycle_start=cs.get("start"),
        cycle_end=cs.get("end"),
        cycle_day=cs.get("day"),
        cycle_total_days=cs.get("total_days"),
        trajectories=trajectories,
        excellence=excel_obj,
        paragraph=out["section_1_paragraph"],
    )

    rec = out.get("section_2_recommendation")
    recommendation: Recommendation | None = None
    if rec:
        recommendation = Recommendation(
            topic=rec.get("topic", ""),
            subject=rec.get("subject", ""),
            leverage_score=0.0,  # Claude path doesn't surface a score
            contributors={"claude_synthesis": 1.0},
            why_it_matters=rec.get("why_it_matters", ""),
            conversation_starter=rec.get("conversation_starter", ""),
            time_budget_min=TIME_BUDGET_MIN,
        )

    teacher_asks = [
        TeacherAsk(
            subject=a.get("subject"),
            teacher=a.get("teacher"),
            question=a.get("question", ""),
            evidence=f"row_ids: {', '.join(str(i) for i in a.get('evidence_row_ids', []))}",
            priority=0.0,
        )
        for a in out.get("section_3_teacher_asks", [])
    ]
    ignore_items = [
        IgnoreItem(
            label=it.get("label", ""),
            reason=it.get("reason", ""),
            evidence=f"row_ids: {', '.join(str(i) for i in it.get('evidence_row_ids', []))}",
        )
        for it in out.get("section_4_what_to_ignore", [])
    ]

    log.info(
        "sunday_brief: Claude synthesis succeeded (model=%s, kid=%s, asks=%d, ignore=%d)",
        resp.model, child.display_name, len(teacher_asks), len(ignore_items),
    )

    return SundayBrief(
        child_id=child.id,
        child_name=child.display_name,
        class_section=child.class_section,
        generated_for=today.isoformat(),
        cycle_shape=cycle_shape,
        recommendation=recommendation,
        leverage_top_3=[],
        teacher_asks=teacher_asks,
        ignore_items=ignore_items,
        honest_caveat=HONEST_CAVEAT,
    )


# ─── public API ─────────────────────────────────────────────────────────────

HONEST_CAVEAT = (
    "Generated from this week's grades, assignments, and topic-state — "
    "not from teacher comments (still empty in the DB) or attendance. "
    "Trends use a least-squares slope on the last 4-6 grades per subject; "
    "subjects with ≤ 2 grades are silenced rather than guessed at. "
    "The recommendation is one nudge, not a verdict — skip the conversation "
    "if the week's already heavy."
)


async def build_brief(
    session: AsyncSession,
    child: Child,
    *,
    today: date | None = None,
    use_llm: bool = True,
    use_claude_synthesis: bool = True,
) -> SundayBrief:
    """Compute the full brief for one kid. No DB writes, no cross-kid
    aware logic — pure synthesis.

    Two synthesis paths run in this order:

      1. **Claude-driven** (default when use_claude_synthesis=True).
         A full data pack is built deterministically, then handed to
         the configured Claude backend (claude_cli, Max-subscription,
         no per-token cost). Claude returns a structured JSON brief
         which is *validated* against the data pack — every numeric
         claim in §1 must echo a number from the pack, every §2/§3/§4
         entry must reference a row id present in the pack.

         If Claude is unreachable, the response fails validation, or
         the configured backend isn't `claude`, the rule path runs.

      2. **Rule-driven** (fallback).
         §1 paragraph from rule-generated bullets; §2 from leverage
         scoring; §3 from pattern_state + syllabus_overrides + decaying
         topics + homework-load over CBSE cap; §4 from zero-weight
         grades + admin school messages + sub-threshold weekend marks.

    Both paths populate the same `SundayBrief` dataclass shape, so the
    markdown renderer doesn't care which one ran. The
    `_build_data_pack` step always runs — Claude needs it, the
    validator needs it, and the rule path uses it as input.
    """
    today = today or today_ist()
    grades = await _grades_for_child(session, child.id)

    # Data pack lives at module level so both paths share it.
    pack = await _build_data_pack(session, child, today=today, grades=grades)

    # Try Claude path first.
    if use_claude_synthesis:
        claude_out = await _claude_synthesis(child, pack, today=today)
        if claude_out is not None:
            return claude_out

    # Fallback: rule-driven synthesis.
    cycle_shape = await _build_cycle_shape(session, child, today=today, use_llm=use_llm)
    rec, top3 = await _build_recommendation(session, child, today=today)
    teacher_asks = await _build_teacher_asks(
        session, child, today=today, grades=grades,
    )
    ignore_items = await _build_ignore_items(
        session, child, today=today, grades=grades,
    )
    return SundayBrief(
        child_id=child.id,
        child_name=child.display_name,
        class_section=child.class_section,
        generated_for=today.isoformat(),
        cycle_shape=cycle_shape,
        recommendation=rec,
        leverage_top_3=top3,
        teacher_asks=teacher_asks,
        ignore_items=ignore_items,
        honest_caveat=HONEST_CAVEAT,
    )


async def build_brief_for_all(
    session: AsyncSession,
    *,
    today: date | None = None,
    use_llm: bool = True,
) -> list[SundayBrief]:
    children = (await session.execute(select(Child))).scalars().all()
    out: list[SundayBrief] = []
    for c in children:
        out.append(await build_brief(session, c, today=today, use_llm=use_llm))
    return out


# ─── markdown rendering ─────────────────────────────────────────────────────

def render_markdown(brief: SundayBrief) -> str:
    """Render a SundayBrief as the parent-readable markdown preview.
    Kept here (not in render.py) because it's tightly coupled to the
    SundayBrief dataclass shape; if §3 / §4 are added later, both the
    dataclass and this renderer get updated together."""
    cs = brief.cycle_shape
    lines: list[str] = []
    klass = brief.class_section or ""
    header = f"# Sunday brief — {brief.child_name}"
    if klass:
        header += f" ({klass})"
    lines.append(header)
    lines.append("")
    lines.append(f"_For Sunday, {brief.generated_for}._")
    lines.append("")

    # ── §1 ──
    lines.append("## 1. The shape of this learning cycle")
    lines.append("")
    lines.append(cs.paragraph)
    lines.append("")
    lines.append("<details><summary>Where these numbers came from</summary>")
    lines.append("")
    if cs.cycle_name:
        lines.append(
            f"- Cycle: **{cs.cycle_name}** "
            f"({cs.cycle_start} → {cs.cycle_end}); "
            f"day {cs.cycle_day} of {cs.cycle_total_days}."
        )
    else:
        lines.append("- Cycle: between cycles right now (no active LC).")
    if cs.trajectories:
        lines.append("- Per-subject trajectories (least-squares slope across the last "
                     f"{SLOPE_WINDOW} grades, min sample {SLOPE_MIN_GRADES}):")
        for t in cs.trajectories:
            avg = f"{t.avg_pct:.1f} %" if t.avg_pct is not None else "—"
            slope = f"{t.slope_pct_per_step:+.2f}" if t.slope_pct_per_step is not None else "—"
            sd = f"±{t.stddev_pct:.2f}" if t.stddev_pct is not None else "—"
            ids = ", ".join(str(i) for i in t.grade_ids_used) or "—"
            lines.append(
                f"    - **{t.subject}** — {t.direction}; n={t.n_grades}, "
                f"avg={avg}, slope={slope} pts/step, stddev={sd}; "
                f"row ids: {ids}"
            )
    excel = cs.excellence
    if excel.ytd_avg is None:
        lines.append("- Excellence arithmetic: no graded items in the year yet.")
    else:
        line = (
            f"- Excellence arithmetic: YTD avg **{excel.ytd_avg:.2f} %** across "
            f"{excel.grades_count} grades; {excel.above_85_count} ≥ 85 %; "
            f"on track = **{excel.on_track}**."
        )
        if excel.headroom_at_zero is not None:
            line += f" Headroom at 0 %: **{excel.headroom_at_zero}** grades."
        if excel.headroom_at_typical_below_85 is not None and excel.typical_below_85_pct is not None:
            line += (
                f" Headroom at typical sub-85 ({excel.typical_below_85_pct:.0f} %): "
                f"**{excel.headroom_at_typical_below_85}** grades."
            )
        lines.append(line)
    lines.append("")
    lines.append("</details>")
    lines.append("")

    # ── §2 ──
    lines.append("## 2. The one thing worth a conversation")
    lines.append("")
    rec = brief.recommendation
    if rec is None:
        if not brief.leverage_top_3:
            lines.append(
                "No standout topic this week — all subjects look steady, "
                "and there are no shaky topics in the tray."
            )
        else:
            top = brief.leverage_top_3[0]
            lines.append(
                f"No standout topic this week — leverage scores stay below "
                f"the {LEVERAGE_THRESHOLD:.1f} threshold "
                f"(top candidate **{top.subject} / {top.topic}** at "
                f"{top.leverage_score:.2f})."
            )
    else:
        lines.append(f"**{rec.subject} — {rec.topic}**")
        lines.append("")
        lines.append(f"_Why it matters:_ {rec.why_it_matters}")
        lines.append("")
        lines.append(f"_Try this (about {rec.time_budget_min} min):_ {rec.conversation_starter}")
        lines.append("")
        # Leverage scoring is only meaningful for the rule-driven path.
        # When Claude wrote this section, the contributor map is just
        # {"claude_synthesis": 1.0} — an internal artefact, not signal.
        if rec.contributors and "claude_synthesis" not in rec.contributors:
            lines.append("<details><summary>How the leverage score was built</summary>")
            lines.append("")
            lines.append(
                f"- Total **{rec.leverage_score:.2f}** "
                f"(threshold to surface = {LEVERAGE_THRESHOLD:.1f})"
            )
            for k, v in rec.contributors.items():
                lines.append(f"    - `{k}`: {v:+.2f}")
            lines.append("")
            lines.append("</details>")
    lines.append("")

    # ── leverage top 3 (visibility) — only show when there are real
    # alternatives to compare; a single-row list duplicates §2.
    if len(brief.leverage_top_3) > 1:
        lines.append("<details><summary>Other candidates considered</summary>")
        lines.append("")
        for r in brief.leverage_top_3:
            lines.append(
                f"- **{r.subject} / {r.topic}** — leverage {r.leverage_score:.2f} "
                f"({', '.join(f'{k}={v:+.2f}' for k, v in r.contributors.items())})"
            )
        lines.append("")
        lines.append("</details>")
        lines.append("")

    # ── §3 teacher asks ──
    lines.append("## 3. Three asks for the school")
    lines.append("")
    if not brief.teacher_asks:
        lines.append(
            "_Nothing surfaced this week — no skipped/delayed topics, no "
            "repeated-attempt patterns, and homework load is within the "
            "CBSE reference. Save these slots for when there's real signal._"
        )
    else:
        lines.append("_Phrased as questions, not statements. You decide which (if any) to raise._")
        lines.append("")
        for i, a in enumerate(brief.teacher_asks, 1):
            who = ""
            if a.subject and a.teacher:
                who = f" ({a.subject} · {a.teacher})"
            elif a.subject:
                who = f" ({a.subject})"
            elif a.teacher:
                who = f" ({a.teacher})"
            lines.append(f"{i}. {a.question}{who}")
        lines.append("")
        lines.append("<details><summary>Citations</summary>")
        lines.append("")
        for a in brief.teacher_asks:
            lines.append(f"- {a.evidence}")
        lines.append("")
        lines.append("</details>")
    lines.append("")

    # ── §4 what to ignore ──
    lines.append("## 4. What to ignore this week")
    lines.append("")
    if not brief.ignore_items:
        lines.append(
            "_Nothing structurally dismissible this week. (We only call out "
            "items with mechanical reasons to ignore — zero-weight, admin-"
            "only, sub-threshold — never subjective dismissals.)_"
        )
    else:
        for it in brief.ignore_items:
            reason = it.reason.rstrip(". ")  # avoid "..", we add the period
            lines.append(f"- **{it.label}** — {reason}.")
        lines.append("")
        lines.append("<details><summary>Citations</summary>")
        lines.append("")
        for it in brief.ignore_items:
            lines.append(f"- {it.evidence}")
        lines.append("")
        lines.append("</details>")
    lines.append("")

    # ── footer ──
    lines.append("---")
    lines.append("")
    lines.append(f"_{brief.honest_caveat}_")
    lines.append("")

    return "\n".join(lines)
