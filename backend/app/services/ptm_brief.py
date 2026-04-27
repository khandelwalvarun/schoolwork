"""PTM (parent-teacher meeting) prep brief.

The Sunday brief generalised to a one-page meeting prep doc, organised
**per subject** because each subject is a separate teacher conversation.
For each subject the parent gets:

  - Current state — 1-2 sentences naming the trajectory
  - Talking points — 2-4 evidence-grounded observations
  - Questions for the teacher — 2-3 phrased as questions, not statements
  - Evidence row ids — Claude must cite

Plus cross-subject sections:
  - Headline — 1 sentence on the kid's overall academic shape
  - General questions — items that span subjects (e.g. homework load,
    cycle-wide observations)
  - Things to ignore — admin / structural dismissals

Same architecture as sunday_brief.py: a deterministic data pack is
built first, fed to Claude with a strict JSON schema, validated against
pack['_row_ids']. Falls back to a rule-based skeleton if Claude is
unreachable / invalid.
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
from .anomaly import detect_anomalies_for_child
from .excellence import EXCELLENCE_THRESHOLD, status_for_child
from .grade_match import _parse_loose_date
from .homework_load import homework_load
from .patterns import list_patterns
from .shaky_topics import shaky_for_child
from .syllabus import (
    cycle_for_date,
    cycle_for_date_merged,
    fuzzy_topic_for,
    normalize_subject,
)
from .topic_state import list_topic_state


log = logging.getLogger(__name__)


@dataclass
class ParentRaised:
    """An item the parent flagged as 'worth a chat' for the PTM. Each
    one renders verbatim — we never let the LLM rephrase the parent's
    own concerns. Claude can still weave these into talking_points if
    relevant, but the parent's list is canonical."""
    item_id: int
    kind: str             # assignment | grade | comment | school_message
    title: str | None
    title_en: str | None
    due_or_date: str | None
    note: str | None      # the parent's reason, free-text

    def to_dict(self) -> dict[str, Any]:
        return {
            "item_id": self.item_id,
            "kind": self.kind,
            "title": self.title,
            "title_en": self.title_en,
            "due_or_date": self.due_or_date,
            "note": self.note,
        }


@dataclass
class SubjectSection:
    name: str
    teacher: str | None
    n_grades: int
    avg_pct: float | None
    direction: str            # rising/falling/volatile/flat/early/insufficient
    current_state: str        # Claude prose
    talking_points: list[str] = field(default_factory=list)
    questions_for_teacher: list[str] = field(default_factory=list)
    evidence_row_ids: list[int] = field(default_factory=list)
    parent_raised: list[ParentRaised] = field(default_factory=list)


@dataclass
class PTMBrief:
    child_id: int
    child_name: str
    class_section: str | None
    as_of: str                # ISO date
    headline: str             # 1-sentence overall
    subjects: list[SubjectSection]
    general_questions: list[str]
    things_to_ignore: list[str]
    # Parent-flagged items that don't fit any single subject (school
    # messages, kind=other comments). Subject-scoped flags hang off
    # SubjectSection.parent_raised. Renders as its own "Worth a chat"
    # block above general questions.
    parent_raised_general: list[ParentRaised]
    honest_caveat: str
    llm_used: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "child_id": self.child_id,
            "child_name": self.child_name,
            "class_section": self.class_section,
            "as_of": self.as_of,
            "headline": self.headline,
            "subjects": [
                {
                    "name": s.name,
                    "teacher": s.teacher,
                    "n_grades": s.n_grades,
                    "avg_pct": s.avg_pct,
                    "direction": s.direction,
                    "current_state": s.current_state,
                    "talking_points": s.talking_points,
                    "questions_for_teacher": s.questions_for_teacher,
                    "evidence_row_ids": s.evidence_row_ids,
                    "parent_raised": [p.to_dict() for p in s.parent_raised],
                }
                for s in self.subjects
            ],
            "general_questions": self.general_questions,
            "things_to_ignore": self.things_to_ignore,
            "parent_raised_general": [p.to_dict() for p in self.parent_raised_general],
            "honest_caveat": self.honest_caveat,
            "llm_used": self.llm_used,
        }


HONEST_CAVEAT = (
    "Generated from Veracross data — grades, assignment bodies, "
    "topic-mastery state, recent patterns, and syllabus coverage. "
    "We don't see what's said in class or read teacher-only notes; "
    "use this as a prep aid, not a verdict."
)


async def _build_pack(
    session: AsyncSession, child: Child, today: date,
) -> dict[str, Any]:
    """Per-subject + cross-subject pack. Every numeric value carries
    its source row id."""
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

    grades = (
        await session.execute(
            select(VeracrossItem)
            .where(VeracrossItem.child_id == child.id)
            .where(VeracrossItem.kind == "grade")
        )
    ).scalars().all()
    asgs = (
        await session.execute(
            select(VeracrossItem)
            .where(VeracrossItem.child_id == child.id)
            .where(VeracrossItem.kind == "assignment")
        )
    ).scalars().all()
    asg_by_id = {a.id: a for a in asgs}

    # Group everything by normalized subject.
    by_subject: dict[str, dict[str, Any]] = {}

    for g in grades:
        try:
            n = json.loads(g.normalized_json or "{}")
        except Exception:
            n = {}
        pct = n.get("grade_pct")
        if pct is None:
            continue
        subj = normalize_subject(g.subject) or g.subject or "Unknown"
        bucket = by_subject.setdefault(subj, {
            "grades": [], "assignments": [], "teacher": None,
        })
        d = _parse_loose_date(g.due_or_date)
        a = asg_by_id.get(g.linked_assignment_id) if g.linked_assignment_id else None
        bucket["grades"].append({
            "row_id": g.id,
            "title": g.title,
            "graded_date": d.isoformat() if d else None,
            "pct": float(pct),
            "score_text": n.get("score_text"),
            "linked_assignment_id": g.linked_assignment_id,
            "linked_assignment_title": a.title if a else None,
            "linked_assignment_body": a.body if a else None,
            "anomaly_explanation": g.llm_summary,  # cached if computed
        })
        # Pick up the teacher field from the most-recent normalized_json.
        tname = n.get("teacher")
        if isinstance(tname, str) and tname.strip() and not bucket["teacher"]:
            bucket["teacher"] = tname.strip()

    for a in asgs:
        d = _parse_loose_date(a.due_or_date)
        if d is None:
            continue
        # Future assignments only (next 21 days) — past assignments
        # are reflected via grades.
        days = (d - today).days
        if days < -3 or days > 21:
            continue
        subj = normalize_subject(a.subject) or a.subject or "Unknown"
        bucket = by_subject.setdefault(subj, {
            "grades": [], "assignments": [], "teacher": None,
        })
        try:
            n = json.loads(a.normalized_json or "{}")
        except Exception:
            n = {}
        bucket["assignments"].append({
            "row_id": a.id,
            "title": a.title,
            "due_date": d.isoformat(),
            "days_from_today": days,
            "body": a.body,
            "the_ask": a.llm_summary,  # populated by assignment_summary if cached
        })
        tname = n.get("teacher")
        if isinstance(tname, str) and tname.strip() and not bucket["teacher"]:
            bucket["teacher"] = tname.strip()

    # Topic mastery — group by subject too.
    topic_states = await list_topic_state(session, child.id)
    for ts in topic_states:
        s = ts.get("subject")
        if not s:
            continue
        bucket = by_subject.setdefault(s, {
            "grades": [], "assignments": [], "teacher": None,
        })
        bucket.setdefault("topic_states", []).append(ts)

    # Parent-flagged "worth a chat" items — the explicit list the parent
    # built up between PTMs. These are CANONICAL: they get rendered
    # verbatim and the LLM can echo them as talking points but never
    # rephrase them. Subject-scoped items hang off the subject bucket;
    # subject-less items (most school messages) fall into a general
    # bucket the renderer surfaces above the cross-subject section.
    flagged = (
        await session.execute(
            select(VeracrossItem)
            .where(VeracrossItem.child_id == child.id)
            .where(VeracrossItem.discuss_with_teacher_at.is_not(None))
            .order_by(VeracrossItem.discuss_with_teacher_at.desc())
        )
    ).scalars().all()
    parent_raised_general: list[dict[str, Any]] = []
    for it in flagged:
        entry = {
            "row_id": it.id,
            "kind": it.kind,
            "title": it.title,
            "title_en": it.title_en,
            "due_or_date": it.due_or_date,
            "note": it.discuss_with_teacher_note,
        }
        subj = normalize_subject(it.subject) if it.subject else None
        if subj and subj in by_subject:
            by_subject[subj].setdefault("parent_raised", []).append(entry)
        elif subj:
            # Subject is set but we have no other signal for it — open
            # a fresh bucket so the parent's flag isn't lost.
            by_subject.setdefault(subj, {
                "grades": [], "assignments": [], "teacher": None,
            }).setdefault("parent_raised", []).append(entry)
        else:
            parent_raised_general.append(entry)

    # Cross-subject signals.
    excellence = (await status_for_child(session, child)).to_dict()
    patterns = await list_patterns(session, child.id)
    cur_month = today.strftime("%Y-%m")
    cur_pat = next((p for p in patterns if p.get("month") == cur_month), None)
    shaky = await shaky_for_child(session, child, limit=None)
    anomalies = await detect_anomalies_for_child(session, child.id)

    try:
        load = await homework_load(session, child, weeks=4)
    except Exception:
        load = None

    cycle_status: dict[str, dict[str, Any]] = {}
    try:
        merged = await cycle_for_date_merged(session, child.class_level, today)
        if merged and merged.topic_status:
            cycle_status = merged.topic_status
    except Exception:
        pass

    pack = {
        "child": {
            "id": child.id,
            "name": child.display_name,
            "class_section": child.class_section,
            "class_level": child.class_level,
        },
        "today": today.isoformat(),
        "current_cycle": cyc_payload,
        "current_cycle_topic_status": cycle_status,
        "by_subject": by_subject,
        "excellence": excellence,
        "pattern_state_current_month": cur_pat,
        "shaky_topics": shaky,
        "off_trend_grades": anomalies,
        "homework_load": load,
        "parent_raised_general": parent_raised_general,
    }

    # _row_ids index for the validator.
    row_ids: set[int] = set()
    for subj, b in by_subject.items():
        for g in b.get("grades", []):
            row_ids.add(int(g["row_id"]))
            if g.get("linked_assignment_id"):
                row_ids.add(int(g["linked_assignment_id"]))
        for a in b.get("assignments", []):
            row_ids.add(int(a["row_id"]))
        for p in b.get("parent_raised", []):
            row_ids.add(int(p["row_id"]))
    for it in anomalies:
        row_ids.add(int(it.get("grade_id", 0)))
    for p in parent_raised_general:
        row_ids.add(int(p["row_id"]))
    pack["_row_ids"] = sorted([r for r in row_ids if r > 0])

    return pack


SYSTEM_PROMPT = """You are the synthesizer for a Parent-Teacher Meeting (PTM) prep brief.

The reader is a parent attending a PTM in the next 1-2 weeks. They want a one-page document organised PER SUBJECT (each subject is a separate teacher conversation), plus a short cross-subject section.

You will receive a JSON DATA PACK with everything we know about this kid:
  - per-subject grades (with bodies and prior anomaly hypotheses), upcoming assignments, topic-mastery states, teacher names
  - per-subject `parent_raised`: items the parent EXPLICITLY flagged as worth discussing — these are CANONICAL questions the parent already wrote down. They will be rendered verbatim under a "Worth a chat" sub-block. You should ALSO weave each one into a question_for_teacher when relevant (echoing the parent's note, not paraphrasing it), and cite its row_id in evidence_row_ids
  - cross-subject: Excellence arithmetic, pattern flags this month, shaky topics, off-trend grades, homework load
  - top-level `parent_raised_general`: subject-less flagged items (typically school messages) — surface these as general_questions when they fit

OUTPUT — strict JSON only, matching this schema:

{
  "headline": "<one sentence naming the kid's overall academic shape>",
  "subjects": [
    {
      "name": "<subject — exactly as in the data pack>",
      "current_state": "<1-2 sentences: trajectory + most-recent grade + topic situation>",
      "talking_points": [
        "<bullet — evidence-grounded observation>",
        "..."
      ],   // 2-4 items
      "questions_for_teacher": [
        "<phrased as a question>",
        "..."
      ],   // 1-3 items
      "evidence_row_ids": [<int>, ...]
    }
  ],
  "general_questions": [
    "<cross-subject question, e.g. about homework cadence, cycle pacing>",
    "..."
  ],   // 0-3 items
  "things_to_ignore": [
    "<a structural dismissal — zero-weight grades, admin messages, etc.>",
    "..."
  ]   // 0-3 items
}

RULES:
- Cover only subjects present in `by_subject`. Skip subjects with zero grades AND zero upcoming assignments AND no shaky topics.
- Order subjects by signal-density: subjects with anomalies, decaying topics, or upcoming high-stakes assignments come FIRST. Subjects that are quiet steady performers go last (or get one bullet "no concerns").
- Every numeric or row-id citation must echo a value present in the pack. Every subject's evidence_row_ids must be a subset of pack['_row_ids'].
- Talking points are OBSERVATIONS, not advice. ("Hindi LC1 carries 2 graded assessments + 1 review due May 1; recent grades cluster 90-95%.")
- Questions are QUESTIONS, not requests. ("Could you share what 'Initial' vs 'Level 1' means in the Guitar rubric?")
- No comparison to the kid's siblings or to other students.
- No behavioural attribution. ("The kid is lazy" / "lacks focus" — forbidden.)
- Headline: ONE sentence. State a trajectory or a tension if there is one; otherwise state quiet steadiness.
- No exclamation marks. Warm, factual.
- Min sample suppression: subjects with ≤2 grades get the "early — too few data points to call a trend" framing.
- Things-to-ignore: ONLY structural reasons (zero-weight, admin-only, sub-threshold pattern). Never subjective dismissals.

Return ONLY the JSON object. No prose outside the braces. No fences."""


def _validate_brief(out: dict[str, Any], pack: dict[str, Any]) -> str | None:
    valid_ids = set(pack.get("_row_ids", []))

    if not isinstance(out.get("headline"), str) or not out["headline"].strip():
        return "headline missing"
    subjects = out.get("subjects")
    if not isinstance(subjects, list):
        return "subjects must be a list"
    valid_subjects = set(pack.get("by_subject", {}).keys())
    for i, s in enumerate(subjects):
        if not isinstance(s, dict):
            return f"subjects[{i}]: not an object"
        nm = s.get("name")
        if nm not in valid_subjects:
            return f"subjects[{i}]: name {nm!r} not in pack.by_subject"
        ids = s.get("evidence_row_ids", [])
        if not isinstance(ids, list):
            return f"subjects[{i}]: evidence_row_ids must be a list"
        for v in ids:
            try:
                vi = int(v)
            except Exception:
                return f"subjects[{i}]: row id {v!r} not int"
            if vi not in valid_ids:
                return f"subjects[{i}]: row id {vi} not in pack"
    for k in ("general_questions", "things_to_ignore"):
        v = out.get(k, [])
        if not isinstance(v, list) or len(v) > 3:
            return f"{k}: must be list of ≤3"
    return None


async def _claude_synthesis(
    pack: dict[str, Any],
) -> dict[str, Any] | None:
    client = LLMClient()
    if not client.enabled():
        log.info("ptm_brief: LLM not enabled")
        return None
    pack_json = json.dumps(pack, default=str, ensure_ascii=False, indent=2)
    prompt = f"DATA PACK:\n```json\n{pack_json}\n```\n\nGenerate the brief."
    try:
        resp = await client.complete(
            purpose="ptm_brief",
            system=SYSTEM_PROMPT,
            prompt=prompt,
            max_tokens=3200,
        )
    except Exception as e:
        log.warning("ptm_brief Claude call failed: %s", e)
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
        log.warning("ptm_brief Claude returned non-JSON: %s; raw=%r", e, text[:300])
        return None
    err = _validate_brief(out, pack)
    if err:
        log.warning("ptm_brief Claude validation failed: %s", err)
        return None
    return out


def _rule_skeleton(pack: dict[str, Any]) -> dict[str, Any]:
    """Mechanical fallback when Claude is unavailable."""
    subjects: list[dict[str, Any]] = []
    for name, b in pack.get("by_subject", {}).items():
        grades = b.get("grades") or []
        n = len(grades)
        parent_raised = b.get("parent_raised") or []
        if n == 0 and not b.get("assignments") and not parent_raised:
            continue
        avg = (
            sum(g.get("pct", 0) for g in grades) / n if n > 0 else None
        )
        tps = []
        if avg is not None:
            tps.append(f"{n} grade{'s' if n != 1 else ''}, avg {avg:.0f} %.")
        upcoming = b.get("assignments") or []
        if upcoming:
            tps.append(f"{len(upcoming)} upcoming in next 21 days.")
        # Translate parent's flagged-item notes into questions verbatim
        # so the rule fallback still surfaces them prominently.
        questions: list[str] = []
        for p in parent_raised:
            note = (p.get("note") or "").strip()
            title = p.get("title_en") or p.get("title") or "this item"
            if note:
                questions.append(f"{note} (re: {title})")
            else:
                questions.append(f"Could you walk me through {title}?")
        subjects.append({
            "name": name,
            "teacher": b.get("teacher"),
            "n_grades": n,
            "avg_pct": avg,
            "direction": "insufficient",
            "current_state": (
                f"{n} grade{'s' if n != 1 else ''} on record"
                + (f", avg {avg:.0f}%." if avg is not None else ".")
            ),
            "talking_points": tps,
            "questions_for_teacher": questions[:3],
            "evidence_row_ids": (
                [g["row_id"] for g in grades[:3]]
                + [int(p["row_id"]) for p in parent_raised[:3] if p.get("row_id")]
            ),
        })
    return {
        "headline": "Brief generated without LLM — see per-subject sections for the data.",
        "subjects": subjects,
        "general_questions": [],
        "things_to_ignore": [],
    }


async def build_ptm_brief(
    session: AsyncSession,
    child: Child,
    *,
    today: date | None = None,
    use_claude: bool = True,
) -> PTMBrief:
    today = today or today_ist()
    pack = await _build_pack(session, child, today)

    out: dict[str, Any] | None = None
    llm_used = False
    if use_claude:
        out = await _claude_synthesis(pack)
        if out is not None:
            llm_used = True
    if out is None:
        out = _rule_skeleton(pack)

    def _to_parent_raised(items: list[dict[str, Any]]) -> list[ParentRaised]:
        return [
            ParentRaised(
                item_id=int(p.get("row_id", 0)),
                kind=p.get("kind") or "assignment",
                title=p.get("title"),
                title_en=p.get("title_en"),
                due_or_date=p.get("due_or_date"),
                note=p.get("note"),
            )
            for p in items
            if int(p.get("row_id", 0)) > 0
        ]

    sections: list[SubjectSection] = []
    seen_subjects: set[str] = set()
    for s in out.get("subjects", []):
        nm = s.get("name", "")
        bucket = pack.get("by_subject", {}).get(nm, {})
        grades = bucket.get("grades") or []
        n = len(grades)
        avg = (sum(g.get("pct", 0) for g in grades) / n) if n > 0 else None
        sections.append(SubjectSection(
            name=nm,
            teacher=bucket.get("teacher"),
            n_grades=n,
            avg_pct=avg,
            direction=s.get("direction", "insufficient"),
            current_state=s.get("current_state", ""),
            talking_points=list(s.get("talking_points", [])),
            questions_for_teacher=list(s.get("questions_for_teacher", [])),
            evidence_row_ids=list(s.get("evidence_row_ids", [])),
            parent_raised=_to_parent_raised(bucket.get("parent_raised") or []),
        ))
        seen_subjects.add(nm)

    # Subjects that have ONLY parent-raised items but nothing else
    # (no grades, no upcoming assignments) get appended so the parent's
    # flagged concerns are never silently dropped.
    for nm, bucket in (pack.get("by_subject") or {}).items():
        if nm in seen_subjects:
            continue
        pr = bucket.get("parent_raised") or []
        if not pr:
            continue
        sections.append(SubjectSection(
            name=nm,
            teacher=bucket.get("teacher"),
            n_grades=len(bucket.get("grades") or []),
            avg_pct=None,
            direction="parent_raised",
            current_state="No graded data — surfaced because you flagged item(s) for this subject.",
            talking_points=[],
            questions_for_teacher=[],
            evidence_row_ids=[int(p.get("row_id", 0)) for p in pr if p.get("row_id")],
            parent_raised=_to_parent_raised(pr),
        ))

    return PTMBrief(
        child_id=child.id,
        child_name=child.display_name,
        class_section=child.class_section,
        as_of=today.isoformat(),
        headline=out.get("headline", ""),
        subjects=sections,
        general_questions=list(out.get("general_questions", [])),
        things_to_ignore=list(out.get("things_to_ignore", [])),
        parent_raised_general=_to_parent_raised(pack.get("parent_raised_general") or []),
        honest_caveat=HONEST_CAVEAT,
        llm_used=llm_used,
    )


def render_markdown(brief: PTMBrief) -> str:
    lines: list[str] = []
    title = f"# PTM brief — {brief.child_name}"
    if brief.class_section:
        title += f" ({brief.class_section})"
    lines.append(title)
    lines.append("")
    lines.append(f"_As of {brief.as_of}._")
    lines.append("")

    if brief.headline:
        lines.append(f"**{brief.headline}**")
        lines.append("")

    for s in brief.subjects:
        h = f"## {s.name}"
        if s.teacher:
            h += f"  ·  {s.teacher}"
        lines.append(h)
        lines.append("")
        if s.current_state:
            lines.append(s.current_state)
            lines.append("")
        if s.talking_points:
            lines.append("**Talking points**")
            for tp in s.talking_points:
                lines.append(f"- {tp}")
            lines.append("")
        if s.questions_for_teacher:
            lines.append("**Questions for the teacher**")
            for q in s.questions_for_teacher:
                lines.append(f"- {q}")
            lines.append("")
        if s.parent_raised:
            lines.append("**💬 Worth a chat — your list**")
            for p in s.parent_raised:
                title = p.title_en or p.title or "(untitled)"
                bullet = f"- _{p.kind}_ — **{title}**"
                if p.due_or_date:
                    bullet += f" ({p.due_or_date})"
                if p.note:
                    bullet += f" → {p.note}"
                lines.append(bullet)
            lines.append("")

    if brief.parent_raised_general:
        lines.append("## 💬 Worth a chat — your list (general)")
        lines.append("")
        for p in brief.parent_raised_general:
            title = p.title_en or p.title or "(untitled)"
            bullet = f"- _{p.kind}_ — **{title}**"
            if p.due_or_date:
                bullet += f" ({p.due_or_date})"
            if p.note:
                bullet += f" → {p.note}"
            lines.append(bullet)
        lines.append("")

    if brief.general_questions:
        lines.append("## General — across subjects")
        lines.append("")
        for q in brief.general_questions:
            lines.append(f"- {q}")
        lines.append("")

    if brief.things_to_ignore:
        lines.append("## What to ignore")
        lines.append("")
        for t in brief.things_to_ignore:
            lines.append(f"- {t}")
        lines.append("")

    lines.append("---")
    lines.append("")
    lines.append(f"_{brief.honest_caveat}_")
    lines.append("")
    return "\n".join(lines)
