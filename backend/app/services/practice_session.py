"""Practice-prep session orchestration.

A session is a stateful prep workspace, not a one-shot generator. The
parent starts a session (subject + topic + optional linked review/test),
the LLM produces an initial draft, then the parent iterates with prompts
("harder", "focus on word problems", "in Hindi", "remove Q3 it's too
easy") and the LLM produces a new draft each round.

Architecture:
    1. Pack — gather grounding context per session:
         - syllabus topics for the kid's class + subject + current cycle
         - kid's recent grades in the subject (calibrate difficulty)
         - kid's topic-mastery state (focus on weak topics)
         - linked review/test row's body + title (the actual prompt)
         - Claude-Vision-extracted text from any classwork scans bound
           to the session (what was ACTUALLY covered in class)
         - prior iteration's output_md + output_json (so the LLM can
           refine, not regenerate from scratch)
         - parent's iterative prompt for THIS round
    2. Synthesize — Claude Opus (purpose='practice_generator') with
       a strict JSON schema we validate before persisting.
    3. Persist — append a PracticeIteration row, advance updated_at,
       cap iteration count at 30 per session for sanity.

The LLM call goes through purpose='practice_generator' so the
LLM_PURPOSE_BACKENDS env var can override Opus per-deployment if
needed. Default model is claude-opus-4-5; override via
PRACTICE_LLM_MODEL in .env.
"""
from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..llm.client import LLMClient
from ..models import (
    Child, PracticeClassworkScan, PracticeIteration, PracticeSession,
    TopicState, VeracrossItem,
)
from ..util.time import today_ist
from .grade_match import _parse_loose_date
from .syllabus import cycle_for_date, normalize_subject


log = logging.getLogger(__name__)


# Default model. Override via .env: PRACTICE_LLM_MODEL=claude-opus-4-5
# (or any Opus identifier the local Claude CLI accepts).
PRACTICE_LLM_MODEL_DEFAULT = "claude-opus-4-5"
MAX_ITERATIONS_PER_SESSION = 30


# ───────────────────────── public API ─────────────────────────

async def start_session(
    session: AsyncSession,
    *,
    child_id: int,
    subject: str,
    topic: str | None = None,
    linked_assignment_id: int | None = None,
    title: str | None = None,
    initial_prompt: str | None = None,
    use_llm: bool = True,
) -> dict[str, Any]:
    """Create a new prep session and run the first iteration.

    Returns the session dict with the first iteration filled in. If
    `use_llm=False` (or the LLM is unreachable), the first iteration
    falls through to a rule skeleton so the workspace is non-empty
    even when offline.
    """
    child = (
        await session.execute(select(Child).where(Child.id == child_id))
    ).scalar_one_or_none()
    if child is None:
        raise ValueError(f"child {child_id} not found")
    subject_norm = normalize_subject(subject) or subject

    auto_title = title or _auto_title(child, subject_norm, topic, linked_assignment_id)
    row = PracticeSession(
        child_id=child_id,
        subject=subject_norm,
        topic=topic,
        linked_assignment_id=linked_assignment_id,
        title=auto_title,
    )
    session.add(row)
    await session.flush()  # populate row.id
    iteration = await _run_iteration(
        session, row, child=child,
        parent_prompt=initial_prompt, use_llm=use_llm,
    )
    if iteration is not None:
        row.preferred_iteration_id = iteration.id
        row.updated_at = datetime.now(tz=timezone.utc)
    await session.commit()
    return await get_session(session, row.id)


async def iterate(
    session: AsyncSession,
    session_id: int,
    *,
    parent_prompt: str,
    use_llm: bool = True,
) -> dict[str, Any]:
    """Append one more iteration steered by `parent_prompt`. Returns
    the session dict including the new iteration."""
    row = (
        await session.execute(
            select(PracticeSession).where(PracticeSession.id == session_id)
        )
    ).scalar_one_or_none()
    if row is None:
        raise ValueError(f"practice session {session_id} not found")
    if row.archived_at is not None:
        raise ValueError(f"session {session_id} is archived; un-archive first")
    existing = (
        await session.execute(
            select(PracticeIteration)
            .where(PracticeIteration.session_id == session_id)
            .order_by(desc(PracticeIteration.iteration_index))
            .limit(1)
        )
    ).scalar_one_or_none()
    if existing and existing.iteration_index >= MAX_ITERATIONS_PER_SESSION:
        raise ValueError(
            f"session {session_id} hit the {MAX_ITERATIONS_PER_SESSION}-iteration cap; "
            f"start a new session"
        )
    if not parent_prompt or not parent_prompt.strip():
        raise ValueError("parent_prompt is required for iteration")

    child = (
        await session.execute(select(Child).where(Child.id == row.child_id))
    ).scalar_one()
    new_iter = await _run_iteration(
        session, row, child=child,
        parent_prompt=parent_prompt.strip(), use_llm=use_llm,
    )
    if new_iter is not None:
        # Default the preferred draft to the most recent — parent can
        # un-prefer to revert to an earlier round.
        row.preferred_iteration_id = new_iter.id
        row.updated_at = datetime.now(tz=timezone.utc)
    await session.commit()
    return await get_session(session, session_id)


async def get_session(
    session: AsyncSession, session_id: int,
) -> dict[str, Any]:
    """Full payload for one prep session including every iteration +
    every bound classwork scan (with extraction summaries)."""
    row = (
        await session.execute(
            select(PracticeSession).where(PracticeSession.id == session_id)
        )
    ).scalar_one_or_none()
    if row is None:
        raise ValueError(f"practice session {session_id} not found")
    iterations = (
        await session.execute(
            select(PracticeIteration)
            .where(PracticeIteration.session_id == session_id)
            .order_by(PracticeIteration.iteration_index)
        )
    ).scalars().all()
    scans = (
        await session.execute(
            select(PracticeClassworkScan)
            .where(PracticeClassworkScan.session_id == session_id)
            .order_by(PracticeClassworkScan.uploaded_at.desc())
        )
    ).scalars().all()
    return {
        "id": row.id,
        "child_id": row.child_id,
        "subject": row.subject,
        "topic": row.topic,
        "linked_assignment_id": row.linked_assignment_id,
        "title": row.title,
        "status": row.status,
        "preferred_iteration_id": row.preferred_iteration_id,
        "created_at": row.created_at.isoformat(),
        "updated_at": row.updated_at.isoformat(),
        "archived_at": row.archived_at.isoformat() if row.archived_at else None,
        "iterations": [_iteration_to_dict(i) for i in iterations],
        "scans": [_scan_to_dict(s) for s in scans],
    }


async def list_sessions(
    session: AsyncSession,
    *,
    child_id: int | None = None,
    subject: str | None = None,
    include_archived: bool = False,
    limit: int = 100,
) -> list[dict[str, Any]]:
    """Listing view — one row per session, latest iteration's stats only."""
    q = select(PracticeSession).order_by(desc(PracticeSession.updated_at))
    if child_id is not None:
        q = q.where(PracticeSession.child_id == child_id)
    if subject:
        q = q.where(PracticeSession.subject == subject)
    if not include_archived:
        q = q.where(PracticeSession.archived_at.is_(None))
    q = q.limit(limit)
    rows = (await session.execute(q)).scalars().all()
    out: list[dict[str, Any]] = []
    for r in rows:
        # Cheap: just count iterations per session.
        iter_count = (
            await session.execute(
                select(PracticeIteration).where(
                    PracticeIteration.session_id == r.id,
                )
            )
        ).scalars().all()
        out.append({
            "id": r.id,
            "child_id": r.child_id,
            "subject": r.subject,
            "topic": r.topic,
            "title": r.title,
            "status": r.status,
            "iteration_count": len(iter_count),
            "linked_assignment_id": r.linked_assignment_id,
            "preferred_iteration_id": r.preferred_iteration_id,
            "created_at": r.created_at.isoformat(),
            "updated_at": r.updated_at.isoformat(),
            "archived_at": r.archived_at.isoformat() if r.archived_at else None,
        })
    return out


async def archive_session(
    session: AsyncSession, session_id: int, archive: bool = True,
) -> dict[str, Any]:
    row = (
        await session.execute(
            select(PracticeSession).where(PracticeSession.id == session_id)
        )
    ).scalar_one_or_none()
    if row is None:
        raise ValueError(f"practice session {session_id} not found")
    row.archived_at = datetime.now(tz=timezone.utc) if archive else None
    row.status = "archived" if archive else "active"
    await session.commit()
    return await get_session(session, session_id)


async def set_preferred(
    session: AsyncSession, iteration_id: int,
) -> dict[str, Any]:
    """Star a specific iteration as the canonical draft for its session."""
    iter_row = (
        await session.execute(
            select(PracticeIteration).where(PracticeIteration.id == iteration_id)
        )
    ).scalar_one_or_none()
    if iter_row is None:
        raise ValueError(f"iteration {iteration_id} not found")
    sess = (
        await session.execute(
            select(PracticeSession).where(PracticeSession.id == iter_row.session_id)
        )
    ).scalar_one()
    sess.preferred_iteration_id = iteration_id
    sess.updated_at = datetime.now(tz=timezone.utc)
    await session.commit()
    return await get_session(session, sess.id)


# ───────────────────────── internals ─────────────────────────

def _auto_title(
    child: Child, subject: str, topic: str | None, linked_assignment_id: int | None,
) -> str:
    parts = [subject]
    if topic:
        parts.append(topic)
    parts.append("prep")
    parts.append(f"— {child.display_name}")
    return " ".join(parts)


def _iteration_to_dict(it: PracticeIteration) -> dict[str, Any]:
    out_json: Any = None
    if it.output_json:
        try:
            out_json = json.loads(it.output_json)
        except Exception:
            out_json = None
    return {
        "id": it.id,
        "session_id": it.session_id,
        "iteration_index": it.iteration_index,
        "parent_prompt": it.parent_prompt,
        "output_md": it.output_md,
        "output_json": out_json,
        "llm_used": bool(it.llm_used),
        "llm_model": it.llm_model,
        "llm_input_tokens": it.llm_input_tokens,
        "llm_output_tokens": it.llm_output_tokens,
        "duration_ms": it.duration_ms,
        "error": it.error,
        "created_at": it.created_at.isoformat() if it.created_at else None,
    }


def _scan_to_dict(s: PracticeClassworkScan) -> dict[str, Any]:
    topics: Any = None
    if s.extracted_topics_json:
        try:
            topics = json.loads(s.extracted_topics_json)
        except Exception:
            topics = None
    return {
        "id": s.id,
        "session_id": s.session_id,
        "child_id": s.child_id,
        "subject": s.subject,
        "attachment_id": s.attachment_id,
        "extracted_summary": s.extracted_summary,
        "extracted_topics": topics,
        "extracted_at": s.extracted_at.isoformat() if s.extracted_at else None,
        "uploaded_at": s.uploaded_at.isoformat() if s.uploaded_at else None,
    }


async def _run_iteration(
    session: AsyncSession,
    sess: PracticeSession,
    *,
    child: Child,
    parent_prompt: str | None,
    use_llm: bool,
) -> PracticeIteration | None:
    """Synthesize one new draft. Always inserts a row — even on failure
    we record the rule skeleton + error so the iteration history is
    complete."""
    pack = await _build_pack(session, sess, child)
    prior = pack.get("prior_iteration")

    next_idx = (
        (await session.execute(
            select(PracticeIteration)
            .where(PracticeIteration.session_id == sess.id)
            .order_by(desc(PracticeIteration.iteration_index))
            .limit(1)
        )).scalar_one_or_none()
    )
    next_index = (next_idx.iteration_index + 1) if next_idx else 1

    out_dict: dict[str, Any] | None = None
    llm_used = False
    llm_model = None
    in_t = out_t = None
    err: str | None = None
    duration_ms = 0
    started = time.monotonic()
    if use_llm:
        try:
            out_dict, llm_used, llm_model, in_t, out_t = await _claude_synthesize(
                pack, parent_prompt=parent_prompt,
            )
        except Exception as e:
            err = repr(e)[:500]
            log.warning("practice generator LLM call failed: %s", e)
    duration_ms = int((time.monotonic() - started) * 1000)
    if out_dict is None:
        out_dict = _rule_skeleton(pack)
    md = _render_markdown(out_dict, pack)

    iter_row = PracticeIteration(
        session_id=sess.id,
        iteration_index=next_index,
        parent_prompt=parent_prompt,
        output_md=md,
        output_json=json.dumps(out_dict, ensure_ascii=False, default=str),
        llm_used=llm_used,
        llm_model=llm_model,
        llm_input_tokens=in_t,
        llm_output_tokens=out_t,
        duration_ms=duration_ms,
        error=err,
    )
    session.add(iter_row)
    await session.flush()
    return iter_row


async def _build_pack(
    session: AsyncSession,
    sess: PracticeSession,
    child: Child,
) -> dict[str, Any]:
    """Assemble grounding context for one iteration."""
    today = today_ist()
    cyc = cycle_for_date(child.class_level, today)
    cycle_topics: list[str] = []
    if cyc:
        for_subject = cyc.topics_by_subject.get(sess.subject) or []
        cycle_topics = list(for_subject)

    # Recent grades — last 6 in this subject.
    grades_q = (
        select(VeracrossItem)
        .where(VeracrossItem.child_id == child.id)
        .where(VeracrossItem.kind == "grade")
        .where(
            (VeracrossItem.subject == sess.subject)
            | (VeracrossItem.subject.like(f"% {sess.subject}"))
        )
        .order_by(desc(VeracrossItem.due_or_date))
        .limit(6)
    )
    grades = (await session.execute(grades_q)).scalars().all()
    recent_grades: list[dict[str, Any]] = []
    for g in grades:
        try:
            n = json.loads(g.normalized_json or "{}")
        except Exception:
            n = {}
        if n.get("grade_pct") is None:
            continue
        d = _parse_loose_date(g.due_or_date)
        recent_grades.append({
            "title": g.title,
            "graded_date": d.isoformat() if d else None,
            "pct": n.get("grade_pct"),
            "score_text": n.get("score_text"),
        })

    # Topic mastery — surface weak / decaying topics in this subject.
    ts_rows = (
        await session.execute(
            select(TopicState)
            .where(TopicState.child_id == child.id)
            .where(TopicState.subject == sess.subject)
        )
    ).scalars().all()
    weak_topics = [
        {"topic": ts.topic, "state": ts.state, "last_score": ts.last_score}
        for ts in ts_rows
        if ts.state in ("attempted", "decaying", "familiar")
    ]

    # Linked assignment context.
    linked_dict: dict[str, Any] | None = None
    if sess.linked_assignment_id:
        linked = (
            await session.execute(
                select(VeracrossItem).where(VeracrossItem.id == sess.linked_assignment_id)
            )
        ).scalar_one_or_none()
        if linked is not None:
            linked_dict = {
                "id": linked.id,
                "title": linked.title,
                "title_en": linked.title_en,
                "due_or_date": linked.due_or_date,
                "body": linked.body,
                "notes_en": linked.notes_en,
            }

    # Classwork scans — extracted summary + topics. Skip raw image bytes
    # (those would balloon the prompt; the summary is what we want).
    scans = (
        await session.execute(
            select(PracticeClassworkScan)
            .where(PracticeClassworkScan.session_id == sess.id)
            .order_by(desc(PracticeClassworkScan.uploaded_at))
        )
    ).scalars().all()
    scan_summaries: list[dict[str, Any]] = []
    for s in scans:
        topics: list[str] | None = None
        if s.extracted_topics_json:
            try:
                topics_obj = json.loads(s.extracted_topics_json)
                if isinstance(topics_obj, list):
                    topics = [str(t) for t in topics_obj][:8]
            except Exception:
                topics = None
        scan_summaries.append({
            "scan_id": s.id,
            "uploaded_at": s.uploaded_at.isoformat() if s.uploaded_at else None,
            "summary": s.extracted_summary,
            "topics_seen": topics,
            "extracted_text_excerpt": (s.extracted_text or "")[:1500],
        })

    # Prior iteration — pass the most-recent draft so the LLM refines
    # rather than regenerating cold.
    prior = (
        await session.execute(
            select(PracticeIteration)
            .where(PracticeIteration.session_id == sess.id)
            .order_by(desc(PracticeIteration.iteration_index))
            .limit(1)
        )
    ).scalar_one_or_none()
    prior_dict: dict[str, Any] | None = None
    if prior is not None:
        try:
            prior_json = json.loads(prior.output_json) if prior.output_json else None
        except Exception:
            prior_json = None
        prior_dict = {
            "iteration_index": prior.iteration_index,
            "parent_prompt": prior.parent_prompt,
            "output_json": prior_json,
            "output_md": prior.output_md[:4000],  # cap to keep prompt size sane
        }

    return {
        "session": {
            "id": sess.id,
            "subject": sess.subject,
            "topic": sess.topic,
            "title": sess.title,
        },
        "child": {
            "id": child.id,
            "name": child.display_name,
            "class_level": child.class_level,
            "class_section": child.class_section,
        },
        "today": today.isoformat(),
        "cycle": (
            {"name": cyc.name, "start": cyc.start.isoformat(), "end": cyc.end.isoformat()}
            if cyc else None
        ),
        "cycle_topics_for_subject": cycle_topics,
        "recent_grades": recent_grades,
        "weak_topics": weak_topics,
        "linked_assignment": linked_dict,
        "classwork_scans": scan_summaries,
        "prior_iteration": prior_dict,
    }


# ───────────────────────── LLM prompt + call ─────────────────────────

SYSTEM_PROMPT = """You are an expert tutor preparing a practice sheet for a school student in India. The tutor is the student's parent — they will hand the printed sheet to the kid for revision.

You receive a JSON DATA PACK with:
  - child: name, class_level (CBSE 4 / 6 / etc.), section
  - subject + optional topic
  - cycle + cycle_topics_for_subject (the school's syllabus topics for the current learning cycle)
  - recent_grades (last few graded items in this subject — calibrate difficulty around these)
  - weak_topics (topic-mastery rows where the kid is shaky — bias questions toward these)
  - linked_assignment (the actual review/test the parent is prepping for; may include the teacher's own brief)
  - classwork_scans (Vision-extracted summaries + topic lists from photos of recent classwork — THIS is the ground-truth for what was covered in class; weight it highly)
  - prior_iteration (the previous draft + the parent's prompt for THIS round; refine that, don't regenerate cold)
  - parent_prompt_for_this_round (string, may be empty for the initial draft)

OUTPUT — strict JSON only, matching this schema:

{
  "title": "<short title for the sheet>",
  "instructions": "<2-3 lines: number of questions, time, materials allowed/disallowed>",
  "questions": [
    {
      "n": <int, 1-based>,
      "stem": "<the question, written for the kid in age-appropriate language>",
      "type": "<recall | application | computation | short_answer | mcq | source_based | hots>",
      "marks": <int>,
      "expected_answer": "<concise expected answer or solution outline>",
      "expected_solution_md": "<optional step-by-step solution in markdown>",
      "topic_ref": "<a topic from cycle_topics_for_subject when possible>"
    },
    ...
  ],
  "answer_key": "<separate plain-text answer key, formatted for the parent to check against>",
  "honest_caveat": "Generated by Claude Opus on <today>. Verify against the textbook and the teacher's class notes — Claude can be wrong about specific facts and conventions."
}

RULES:
- Tailor difficulty to recent_grades. If the kid scored 60-75% on recent items in this subject, aim mostly mid-difficulty with 1-2 easy warm-ups; if 85%+, lean harder.
- WEIGHT classwork_scans HEAVILY — those photos show what the teacher actually taught. If a scan mentions a specific worked-example or vocabulary, mirror that style.
- Mix question types: ~30% recall / ~40% application / ~20% short_answer / ~10% HOTS. Adjust per subject (Math is heavier on computation, English on writing/reading).
- For Hindi / Sanskrit / non-Latin subjects: write the question in the appropriate script. Provide an English transliteration in `expected_solution_md` so the parent can follow.
- When the parent's prompt for this round contains an instruction (e.g. "harder", "remove Q3", "more word problems", "make it Hindi-only"), apply it to the prior_iteration verbatim — preserve the unchanged questions, only modify what the parent asked.
- Total marks: aim for 20-30 unless the parent says otherwise.
- Cite a topic_ref for every question when the topic is in cycle_topics_for_subject. Otherwise leave topic_ref="" — DO NOT invent topics.
- Honest_caveat is REQUIRED — must include the model name (Claude Opus) and the date. Never claim authoritative correctness; this is a prep aid, not a graded paper.
- Return ONLY the JSON object. No prose outside the braces. No code fences."""


async def _claude_synthesize(
    pack: dict[str, Any],
    parent_prompt: str | None,
) -> tuple[dict[str, Any] | None, bool, str | None, int | None, int | None]:
    """Call Claude Opus. Returns (parsed_dict, llm_used, model, in_tokens, out_tokens).
    On any failure (LLM unreachable, JSON parse, validation), returns
    (None, False, model, None, None) so the caller falls through to
    the rule skeleton."""
    from ..config import get_settings
    settings = get_settings()
    client = LLMClient()
    if not client.enabled():
        return None, False, None, None, None
    model = (
        getattr(settings, "practice_llm_model", "")
        or PRACTICE_LLM_MODEL_DEFAULT
    )
    pack_for_llm = {**pack, "parent_prompt_for_this_round": parent_prompt or ""}
    prompt = (
        "DATA PACK:\n```json\n"
        + json.dumps(pack_for_llm, default=str, ensure_ascii=False, indent=2)
        + "\n```\n\nGenerate the practice sheet."
    )
    try:
        resp = await client.complete(
            purpose="practice_generator",
            system=SYSTEM_PROMPT,
            prompt=prompt,
            model=model,
            max_tokens=4500,
        )
    except Exception as e:
        log.warning("practice_generator: LLM call failed: %s", e)
        return None, False, model, None, None
    text = (resp.text or "").strip()
    # Strip code fences if Opus added them despite the instruction.
    if text.startswith("```"):
        parts = text.split("```", 2)
        if len(parts) >= 2:
            text = parts[1]
            if text.lstrip().startswith("json"):
                text = text.split("\n", 1)[1] if "\n" in text else text
    try:
        out = json.loads(text)
    except Exception as e:
        log.warning("practice_generator: bad JSON: %s; raw=%r", e, text[:300])
        return None, False, resp.model, resp.input_tokens, resp.output_tokens
    err = _validate(out)
    if err:
        log.warning("practice_generator: validation failed: %s", err)
        return None, False, resp.model, resp.input_tokens, resp.output_tokens
    return out, True, resp.model, resp.input_tokens, resp.output_tokens


def _validate(out: dict[str, Any]) -> str | None:
    if not isinstance(out, dict):
        return "output is not an object"
    if not isinstance(out.get("title"), str) or not out["title"].strip():
        return "title missing"
    if not isinstance(out.get("questions"), list) or not out["questions"]:
        return "questions must be a non-empty list"
    for i, q in enumerate(out["questions"]):
        if not isinstance(q, dict):
            return f"questions[{i}]: not an object"
        if not isinstance(q.get("stem"), str) or not q["stem"].strip():
            return f"questions[{i}]: stem missing"
        try:
            int(q.get("n", i + 1))
            int(q.get("marks", 1))
        except (TypeError, ValueError):
            return f"questions[{i}]: n/marks must be int"
    if not isinstance(out.get("honest_caveat"), str) or not out["honest_caveat"].strip():
        return "honest_caveat is required"
    return None


def _rule_skeleton(pack: dict[str, Any]) -> dict[str, Any]:
    """Mechanical fallback — used when the LLM is unreachable or returns
    invalid JSON. Produces enough structure that the workspace UI is
    non-empty; the parent can iterate from there."""
    sess = pack.get("session", {})
    cyc_topics = pack.get("cycle_topics_for_subject", []) or []
    seed_topics = cyc_topics[:6] if cyc_topics else ["(topic not yet identified)"]
    questions = []
    for i, t in enumerate(seed_topics, 1):
        questions.append({
            "n": i,
            "stem": f"Write what you know about “{t}”. (3-5 sentences.)",
            "type": "short_answer",
            "marks": 3,
            "expected_answer": "(parent: fill from textbook)",
            "expected_solution_md": "",
            "topic_ref": t,
        })
    return {
        "title": sess.get("title") or "Practice prep",
        "instructions": "5-6 short answers. Allow 30 minutes.",
        "questions": questions,
        "answer_key": "(LLM unavailable — answer key not generated.)",
        "honest_caveat": (
            "Rule-based skeleton — LLM was unavailable. Verify against the "
            "textbook before handing this to the kid."
        ),
    }


def _render_markdown(out: dict[str, Any], pack: dict[str, Any]) -> str:
    """Render the structured output as a parent-printable markdown sheet."""
    lines: list[str] = []
    title = out.get("title", "Practice prep")
    child = pack.get("child", {})
    sess = pack.get("session", {})
    lines.append(f"# {title}")
    if child.get("name"):
        cls = child.get("class_level")
        cls_section = pack.get("child", {}).get("class_section")
        sub = sess.get("subject", "")
        bits = [f"**{child['name']}**"]
        if cls is not None:
            bits.append(f"Class {cls}{(' ' + cls_section) if cls_section else ''}")
        if sub:
            bits.append(sub)
        lines.append(" · ".join(bits))
    lines.append("")
    if out.get("instructions"):
        lines.append(f"_{out['instructions']}_")
        lines.append("")

    for q in out.get("questions", []):
        n = q.get("n", "?")
        stem = q.get("stem", "")
        marks = q.get("marks")
        topic = q.get("topic_ref")
        head_bits = [f"**Q{n}.**", stem]
        if marks:
            head_bits.append(f"_({marks} marks)_")
        lines.append(" ".join(head_bits))
        if topic:
            lines.append(f"<sub>{topic}</sub>")
        lines.append("")

    if out.get("answer_key"):
        lines.append("---")
        lines.append("## Answer key")
        lines.append("")
        lines.append(out["answer_key"])
        lines.append("")

    lines.append("---")
    lines.append(f"_{out.get('honest_caveat', '')}_")
    return "\n".join(lines)
