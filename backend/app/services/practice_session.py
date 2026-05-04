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

# Three flavours of session, all flowing through the same iterate loop:
#   review_prep      — generates a practice sheet of questions
#   assignment_help  — generates support material for an existing
#                      assignment (outline / hints / worked example /
#                      reading guide / brainstorm starter)
#   review_work      — reviews the kid's COMPLETED work (uploaded as
#                      student_work scans) for correctness, gives
#                      per-question feedback + suggestions
KIND_REVIEW_PREP = "review_prep"
KIND_ASSIGNMENT_HELP = "assignment_help"
KIND_REVIEW_WORK = "review_work"
ALLOWED_KINDS = {KIND_REVIEW_PREP, KIND_ASSIGNMENT_HELP, KIND_REVIEW_WORK}


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
    kind: str = KIND_REVIEW_PREP,
    use_llm: bool = True,
) -> dict[str, Any]:
    """Create a new prep session and run the first iteration.

    `kind` selects the LLM prompt: KIND_REVIEW_PREP (default) generates
    a practice sheet of questions; KIND_ASSIGNMENT_HELP generates
    support material for an existing assignment. Both share the same
    iteration / scan / preferred-pointer plumbing.

    Returns the session dict with the first iteration filled in. If
    `use_llm=False` (or the LLM is unreachable), the first iteration
    falls through to a rule skeleton so the workspace is non-empty
    even when offline.
    """
    if kind not in ALLOWED_KINDS:
        raise ValueError(f"kind must be one of {sorted(ALLOWED_KINDS)}, got {kind!r}")
    child = (
        await session.execute(select(Child).where(Child.id == child_id))
    ).scalar_one_or_none()
    if child is None:
        raise ValueError(f"child {child_id} not found")
    subject_norm = normalize_subject(subject) or subject

    auto_title = title or _auto_title(child, subject_norm, topic, linked_assignment_id, kind)
    row = PracticeSession(
        child_id=child_id,
        subject=subject_norm,
        topic=topic,
        linked_assignment_id=linked_assignment_id,
        title=auto_title,
        kind=kind,
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
    pinned_sources: list[dict[str, Any]] = []
    if row.pinned_sources_json:
        try:
            decoded = json.loads(row.pinned_sources_json)
            if isinstance(decoded, list):
                pinned_sources = decoded
        except Exception:
            pinned_sources = []
    return {
        "id": row.id,
        "child_id": row.child_id,
        "subject": row.subject,
        "topic": row.topic,
        "linked_assignment_id": row.linked_assignment_id,
        "title": row.title,
        "kind": row.kind,
        "status": row.status,
        "preferred_iteration_id": row.preferred_iteration_id,
        "pinned_sources": pinned_sources,
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
            "kind": r.kind,
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


_VALID_SOURCE_TYPES = {"library", "resource", "syllabus_topic"}


async def set_pinned_sources(
    session: AsyncSession,
    session_id: int,
    sources: list[dict[str, Any]],
) -> dict[str, Any]:
    """Replace the pinned-sources list on a session.

    Each source is {type, ref, label}:
      type=library         ref=<library_id> (int)
      type=resource        ref="scope/category/filename" (e.g. "schoolwide/spellbee/list07.pdf")
      type=syllabus_topic  ref=<topic name string>
    Validates types but doesn't fetch content here — the pack-builder
    pulls extracted text on each iteration so the prompt always sees
    the latest version of the file.
    """
    row = (
        await session.execute(
            select(PracticeSession).where(PracticeSession.id == session_id)
        )
    ).scalar_one_or_none()
    if row is None:
        raise ValueError(f"practice session {session_id} not found")
    cleaned: list[dict[str, Any]] = []
    for s in sources or []:
        if not isinstance(s, dict):
            continue
        t = (s.get("type") or "").strip()
        if t not in _VALID_SOURCE_TYPES:
            continue
        ref = s.get("ref")
        if ref is None:
            continue
        label = (s.get("label") or "").strip() or str(ref)
        cleaned.append({"type": t, "ref": ref, "label": label[:200]})
    row.pinned_sources_json = (
        json.dumps(cleaned, ensure_ascii=False) if cleaned else None
    )
    row.updated_at = datetime.now(tz=timezone.utc)
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
    child: Child, subject: str, topic: str | None,
    linked_assignment_id: int | None, kind: str = KIND_REVIEW_PREP,
) -> str:
    parts = [subject]
    if topic:
        parts.append(topic)
    if kind == KIND_ASSIGNMENT_HELP:
        parts.append("help")
    elif kind == KIND_REVIEW_WORK:
        parts.append("check")
    else:
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
        "purpose": s.purpose,
        "extracted_summary": s.extracted_summary,
        "extracted_topics": topics,
        "extracted_text_present": bool(s.extracted_text),
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
                pack, parent_prompt=parent_prompt, kind=sess.kind,
            )
        except Exception as e:
            err = repr(e)[:500]
            log.warning("practice generator LLM call failed: %s", e)
    duration_ms = int((time.monotonic() - started) * 1000)
    if out_dict is None:
        out_dict = _rule_skeleton(pack, kind=sess.kind)
    md = _render_markdown(out_dict, pack, kind=sess.kind)

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

    # Scans — split by purpose. classwork_reference becomes grounding
    # for the practice generator; student_work goes into a separate
    # bucket the review_work prompt reads as the kid's actual answers.
    scans = (
        await session.execute(
            select(PracticeClassworkScan)
            .where(PracticeClassworkScan.session_id == sess.id)
            .order_by(desc(PracticeClassworkScan.uploaded_at))
        )
    ).scalars().all()

    def _scan_to_summary(s: PracticeClassworkScan) -> dict[str, Any]:
        topics: list[str] | None = None
        if s.extracted_topics_json:
            try:
                topics_obj = json.loads(s.extracted_topics_json)
                if isinstance(topics_obj, list):
                    topics = [str(t) for t in topics_obj][:8]
            except Exception:
                topics = None
        return {
            "scan_id": s.id,
            "uploaded_at": s.uploaded_at.isoformat() if s.uploaded_at else None,
            "summary": s.extracted_summary,
            "topics_seen": topics,
            "extracted_text_excerpt": (s.extracted_text or "")[:1500],
        }

    scan_summaries = [
        _scan_to_summary(s) for s in scans
        if s.purpose == "classwork_reference"
    ]
    student_work_summaries = [
        _scan_to_summary(s) for s in scans
        if s.purpose == "student_work"
    ]

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

    # Pinned sources — pulls extracted text from library/resource files
    # so the LLM sees real grounding content, plus a list of pinned
    # syllabus topics it should weight extra.
    pinned_sources: list[dict[str, Any]] = []
    if sess.pinned_sources_json:
        try:
            decoded = json.loads(sess.pinned_sources_json)
            if isinstance(decoded, list):
                pinned_sources = decoded
        except Exception:
            pinned_sources = []
    pinned_with_content = await _resolve_pinned_sources(pinned_sources)
    pinned_syllabus_topics = [
        s.get("label") or str(s.get("ref"))
        for s in pinned_sources
        if s.get("type") == "syllabus_topic"
    ]

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
        "pinned_syllabus_topics": pinned_syllabus_topics,
        "recent_grades": recent_grades,
        "weak_topics": weak_topics,
        "linked_assignment": linked_dict,
        "classwork_scans": scan_summaries,
        "student_work_scans": student_work_summaries,
        "pinned_sources": pinned_with_content,
        "prior_iteration": prior_dict,
    }


# Per-source content cap so a single pinned PDF doesn't blow up the
# prompt. 8 KB ≈ 1.5-2k tokens, enough for a chapter outline / list /
# excerpt; the LLM gets the gist without paying for the whole textbook.
_PINNED_CONTENT_CAP_CHARS = 8_000


async def _resolve_pinned_sources(
    sources: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """For each pinned source, fetch its content into the pack.
    Library / resource files: extract text up to the cap. Syllabus
    topic pins: just keep the label (handled in the caller). On any
    failure (file missing, decode error, etc.) we still emit the
    source row with content="" + a note so the LLM is aware of the
    pin even if extraction failed."""
    out: list[dict[str, Any]] = []
    for src in sources:
        if not isinstance(src, dict):
            continue
        t = src.get("type")
        ref = src.get("ref")
        label = src.get("label") or str(ref)
        if t == "syllabus_topic":
            # Topic pins are also surfaced via pinned_syllabus_topics
            # — repeat them here so a parent reading the pack as one
            # blob doesn't have to cross-reference.
            out.append({
                "type": t, "ref": ref, "label": label,
                "content_excerpt": "", "note": "syllabus topic pin",
            })
            continue
        if t == "library":
            try:
                content = await _read_library_text(int(ref))
            except Exception as e:
                content, note = "", f"library read failed: {e!r}"[:200]
            else:
                note = None
            out.append({
                "type": t, "ref": ref, "label": label,
                "content_excerpt": content[:_PINNED_CONTENT_CAP_CHARS],
                "note": note,
                "truncated": len(content) > _PINNED_CONTENT_CAP_CHARS,
            })
            continue
        if t == "resource":
            try:
                content = await _read_resource_text(str(ref))
            except Exception as e:
                content, note = "", f"resource read failed: {e!r}"[:200]
            else:
                note = None
            out.append({
                "type": t, "ref": ref, "label": label,
                "content_excerpt": content[:_PINNED_CONTENT_CAP_CHARS],
                "note": note,
                "truncated": len(content) > _PINNED_CONTENT_CAP_CHARS,
            })
            continue
    return out


async def _read_library_text(library_id: int) -> str:
    """Pull a textual snapshot of a library row. Reuses the existing
    classify pipeline's text-extraction (handles PDF / EPUB / DOCX /
    plain text) and falls through to plain bytes for unknown types.
    extract_text_for is sync; we wrap in to_thread so we don't block
    the asyncio loop on a big PDF parse."""
    import asyncio
    from ..config import REPO_ROOT
    from ..db import get_async_session
    from .library import get_library_row
    from .library_classify import extract_text_for
    async with get_async_session() as s:
        row = await get_library_row(s, library_id)
    if row is None or not row.local_path:
        return ""
    path = (REPO_ROOT / row.local_path).resolve()
    if not path.exists():
        return ""
    try:
        text = await asyncio.to_thread(extract_text_for, path, row.mime_type)
        return text or ""
    except Exception:
        try:
            return path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            return ""


async def _read_resource_text(ref: str) -> str:
    """Resource refs are 'scope/category/filename' strings. We only
    auto-extract for plain-text-ish files; PDFs and binaries return
    empty (the file's existence is enough signal for the pack)."""
    from ..config import REPO_ROOT
    parts = ref.split("/", 2)
    if len(parts) != 3:
        return ""
    scope, category, filename = parts
    from .resources_index import resolve_schoolwide, resolve_kid
    # Resource refs include the kid slug for kid scope. Split it off.
    if scope == "schoolwide":
        path = resolve_schoolwide(category, filename)
    else:
        # ref shape for kid scope: "kid/<slug>/<category>/<filename>"
        # Parse defensively — if the caller used three parts treat it
        # as schoolwide; the picker should always give us the right
        # shape for kid resources via the dedicated picker.
        return ""
    if path is None or not path.exists():
        return ""
    suffix = path.suffix.lower()
    if suffix in {".txt", ".md", ".csv", ".json", ".html", ".xml"}:
        try:
            return path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            return ""
    return ""


# ───────────────────────── LLM prompt + call ─────────────────────────

REVIEW_PREP_SYSTEM_PROMPT = """You are an expert tutor preparing a practice sheet for a school student in India. The tutor is the student's parent — they will hand the printed sheet to the kid for revision.

You receive a JSON DATA PACK with:
  - child: name, class_level (CBSE 4 / 6 / etc.), section
  - subject + optional topic
  - cycle + cycle_topics_for_subject (the school's syllabus topics for the current learning cycle)
  - pinned_syllabus_topics (the parent has pinned these — focus questions HERE; over-index vs the broader cycle list)
  - pinned_sources (parent-curated grounding — library files / resource files with content_excerpt + label; these are AUTHORITATIVE source material the parent wants the practice to mirror)
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


ASSIGNMENT_HELP_SYSTEM_PROMPT = """You are an expert tutor helping a parent in India support their child on a SPECIFIC ASSIGNMENT that has already been given by the school. The parent will read your output, understand the assignment, and decide how to walk the kid through it.

You are NOT generating a practice paper. You are generating SUPPORT MATERIAL — an outline, sample, hint sheet, vocabulary list, worked example, brainstorm starter — whatever fits this assignment best. The parent's iterative prompt steers the shape: "give me an outline", "show a worked example", "what should the intro paragraph look like?", "shorter", "in Hindi", "less hand-holding".

You receive a JSON DATA PACK with:
  - child: name, class_level (CBSE 4 / 6 / etc.), section
  - subject + optional topic
  - linked_assignment: title, body, notes_en, due date — read this CAREFULLY; it's the actual ask
  - cycle + cycle_topics_for_subject (current syllabus)
  - pinned_syllabus_topics (parent pinned these — focus help around them)
  - pinned_sources (library / resource files the parent pinned, with content_excerpt — quote / summarise / build from these directly when relevant)
  - recent_grades (last few graded items in this subject — calibrate language level)
  - weak_topics (topic-mastery rows where the kid is shaky)
  - classwork_scans (Vision-extracted summaries from photos of recent classwork — what's been covered)
  - prior_iteration (previous draft + parent's prompt for THIS round; refine, don't regenerate)
  - parent_prompt_for_this_round (string; may be empty for the initial draft)

OUTPUT — strict JSON only, matching this schema:

{
  "title": "<short title — usually echoes the assignment title>",
  "summary": "<1-2 sentence plain-English restatement of what the kid is being asked to do>",
  "format": "<one of: outline | worked_example | hints | starter | reading_guide | brainstorm | vocab | discussion>",
  "sections": [
    {
      "heading": "<short heading>",
      "body_md": "<markdown body — paragraphs, lists, code blocks, etc. as appropriate>",
      "kind": "<step | example | hint | warning | optional | reference>"
    },
    ...
  ],
  "next_steps": [
    "<concrete instruction the parent or kid does next>",
    "..."
  ],
  "honest_caveat": "Generated by Claude Opus on <today>. This is a starting point — verify against the textbook and the teacher's brief."
}

RULES:
- "format" reflects what the parent asked for. Default to "outline" for writing assignments, "worked_example" for math/science problem sets, "hints" for unclear-to-the-kid tasks, "reading_guide" for reading homework, "brainstorm" for project starters.
- Stay GROUNDED in the linked_assignment — quote phrases from its body when they pin down the ask.
- Weight classwork_scans heavily — they show the language and approach the teacher used.
- For Hindi / Sanskrit / non-Latin subjects, write in the appropriate script. Provide an English transliteration in the section body when helpful.
- Apply the parent's iterative prompt as a refinement over prior_iteration — preserve unchanged sections, modify only what was asked.
- DO NOT do the kid's work for them. Outlines and worked examples should illustrate the method, not provide the final answer the kid is meant to discover.
- next_steps is concrete and short (1-4 items). Always present even when empty list.
- honest_caveat is REQUIRED — model name + date.
- Return ONLY the JSON object. No prose outside the braces. No code fences."""


REVIEW_WORK_SYSTEM_PROMPT = """You are an expert tutor reviewing a school student's COMPLETED ASSIGNMENT in India. The parent has uploaded photos of the kid's actual work; Vision has transcribed it into the `student_work_scans` field. Your job: tell the parent what the kid got right, what they got wrong, and what to do next.

You receive a JSON DATA PACK with:
  - child: name, class_level, section
  - subject + optional topic
  - linked_assignment: title, body — the original ask
  - cycle_topics_for_subject (curriculum context)
  - recent_grades (calibrate severity of feedback)
  - classwork_scans (what was covered in class — NOT what the kid did)
  - student_work_scans (THE KID'S ACTUAL ANSWERS — read these CAREFULLY)
  - prior_iteration (previous review draft + parent's prompt for THIS round)
  - parent_prompt_for_this_round (string; e.g. "be gentler", "focus on Q3", "in Hindi")

OUTPUT — strict JSON only, matching this schema:

{
  "title": "<short title — usually 'Review of <assignment title>'>",
  "overall_assessment": "<2-3 sentences: what did the kid get? where did they struggle? overall direction.>",
  "estimated_score": {
    "value": <number, your estimate of marks awarded>,
    "max": <number, total marks>,
    "confidence": "<high | medium | low>"
  } | null,
  "by_question": [
    {
      "ref": "<short label, e.g. 'Q1' or 'Page 2 — math problem 3' or 'paragraph opener'>",
      "verdict": "<correct | partially_correct | incorrect | unclear>",
      "what_kid_did": "<1-2 sentences quoting the kid's answer>",
      "feedback": "<plain-English explanation; if wrong, say WHY in a way an 8-year-old can follow>",
      "suggestion": "<concrete next step the parent / kid can do; null if not applicable>" | null
    },
    ...
  ],
  "general_suggestions": [
    "<across-the-board pointer for the parent — e.g. 'practise place value', 'review tense agreement'>",
    "..."
  ],
  "honest_caveat": "Generated by Claude Opus on <today>. This is an AI review based on photo transcription — handwriting / unusual layouts can be mis-read. Re-check anything graded 'incorrect' before correcting the kid."
}

RULES:
- BE KIND. The kid may be 8 years old. Frame mistakes as learning moments, not failures.
- BE SPECIFIC. "Q3 is wrong because 0.5 + 0.7 ≠ 0.12 — you forgot to carry from the tenths to the ones place." Not just "wrong, try again."
- For non-Latin subjects (Hindi, Sanskrit), respond in the appropriate script. Provide an English transliteration for parents who don't read it.
- When the kid's answer is unreadable in the scan, mark verdict="unclear" and suggest the parent re-photograph that page.
- estimated_score is OPTIONAL — set to null when there's no clean way to score (creative writing, open-ended assignments).
- general_suggestions is small (1-3 items) and actionable.
- Apply parent's iterative prompt to refine the prior_iteration; preserve unchanged feedback, modify only what was asked.
- If `student_work_scans` is empty, output ONE by_question entry with verdict="unclear" explaining no scans were uploaded yet.
- honest_caveat is REQUIRED — model name + date + AI-vision disclaimer.
- Return ONLY the JSON object. No prose outside braces. No code fences."""


async def _claude_synthesize(
    pack: dict[str, Any],
    parent_prompt: str | None,
    kind: str = KIND_REVIEW_PREP,
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
    if kind == KIND_ASSIGNMENT_HELP:
        system_prompt = ASSIGNMENT_HELP_SYSTEM_PROMPT
        purpose = "assignment_help"
        closing_line = "Generate the help material."
    elif kind == KIND_REVIEW_WORK:
        system_prompt = REVIEW_WORK_SYSTEM_PROMPT
        purpose = "review_work"
        closing_line = "Generate the review."
    else:
        system_prompt = REVIEW_PREP_SYSTEM_PROMPT
        purpose = "practice_generator"
        closing_line = "Generate the practice sheet."
    prompt = (
        "DATA PACK:\n```json\n"
        + json.dumps(pack_for_llm, default=str, ensure_ascii=False, indent=2)
        + f"\n```\n\n{closing_line}"
    )
    try:
        resp = await client.complete(
            purpose=purpose,
            system=system_prompt,
            prompt=prompt,
            model=model,
            max_tokens=4500,
        )
    except Exception as e:
        log.warning("%s: LLM call failed: %s", purpose, e)
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
        log.warning("%s: bad JSON: %s; raw=%r", purpose, e, text[:300])
        return None, False, resp.model, resp.input_tokens, resp.output_tokens
    err = _validate(out, kind=kind)
    if err:
        log.warning("%s: validation failed: %s", purpose, err)
        return None, False, resp.model, resp.input_tokens, resp.output_tokens
    return out, True, resp.model, resp.input_tokens, resp.output_tokens


_VALID_VERDICTS = {"correct", "partially_correct", "incorrect", "unclear"}


def _validate(out: dict[str, Any], *, kind: str = KIND_REVIEW_PREP) -> str | None:
    if not isinstance(out, dict):
        return "output is not an object"
    if not isinstance(out.get("title"), str) or not out["title"].strip():
        return "title missing"
    if kind == KIND_ASSIGNMENT_HELP:
        if not isinstance(out.get("sections"), list) or not out["sections"]:
            return "sections must be a non-empty list"
        for i, s in enumerate(out["sections"]):
            if not isinstance(s, dict):
                return f"sections[{i}]: not an object"
            if not isinstance(s.get("heading"), str) or not s["heading"].strip():
                return f"sections[{i}]: heading missing"
            if not isinstance(s.get("body_md"), str) or not s["body_md"].strip():
                return f"sections[{i}]: body_md missing"
        if not isinstance(out.get("next_steps"), list):
            return "next_steps must be a list (may be empty)"
    elif kind == KIND_REVIEW_WORK:
        if not isinstance(out.get("overall_assessment"), str) or not out["overall_assessment"].strip():
            return "overall_assessment missing"
        items = out.get("by_question")
        if not isinstance(items, list) or not items:
            return "by_question must be a non-empty list"
        for i, q in enumerate(items):
            if not isinstance(q, dict):
                return f"by_question[{i}]: not an object"
            if not isinstance(q.get("ref"), str) or not q["ref"].strip():
                return f"by_question[{i}]: ref missing"
            if q.get("verdict") not in _VALID_VERDICTS:
                return f"by_question[{i}]: verdict must be one of {sorted(_VALID_VERDICTS)}"
            if not isinstance(q.get("what_kid_did"), str):
                return f"by_question[{i}]: what_kid_did must be a string"
            if not isinstance(q.get("feedback"), str):
                return f"by_question[{i}]: feedback must be a string"
        gs = out.get("general_suggestions")
        if gs is not None and not isinstance(gs, list):
            return "general_suggestions must be a list (or omitted)"
        score = out.get("estimated_score")
        if score is not None and not isinstance(score, dict):
            return "estimated_score must be an object or null"
    else:
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


def _rule_skeleton(
    pack: dict[str, Any], *, kind: str = KIND_REVIEW_PREP,
) -> dict[str, Any]:
    """Mechanical fallback — used when the LLM is unreachable or returns
    invalid JSON. Produces enough structure that the workspace UI is
    non-empty; the parent can iterate from there."""
    sess = pack.get("session", {})
    if kind == KIND_REVIEW_WORK:
        linked = pack.get("linked_assignment") or {}
        student_scans = pack.get("student_work_scans") or []
        if not student_scans:
            return {
                "title": sess.get("title") or "Work review",
                "overall_assessment": (
                    "No completed work uploaded yet. Upload photos of the kid's "
                    "answers via the 📷 button or drag-drop, then iterate."
                ),
                "estimated_score": None,
                "by_question": [{
                    "ref": "(no scans)",
                    "verdict": "unclear",
                    "what_kid_did": "",
                    "feedback": "No student-work scans on this session yet.",
                    "suggestion": "Upload photos of completed pages and iterate.",
                }],
                "general_suggestions": [],
                "honest_caveat": (
                    "Rule-based skeleton — no scans + LLM unavailable. "
                    "Upload scans and iterate to get a real review."
                ),
            }
        return {
            "title": sess.get("title") or "Work review",
            "overall_assessment": (
                f"{len(student_scans)} page(s) of completed work uploaded. "
                "LLM was unavailable so this is a placeholder — iterate via the "
                "prompt box once Claude Opus is reachable."
            ),
            "estimated_score": None,
            "by_question": [{
                "ref": f"Scan #{s.get('scan_id')}",
                "verdict": "unclear",
                "what_kid_did": (s.get("summary") or "").strip()[:200],
                "feedback": "Awaiting LLM review.",
                "suggestion": None,
            } for s in student_scans],
            "general_suggestions": [],
            "honest_caveat": (
                "Rule-based skeleton — LLM was unavailable. Iterate via the "
                "prompt box once it's reachable for real feedback."
            ),
        }

    if kind == KIND_ASSIGNMENT_HELP:
        linked = pack.get("linked_assignment") or {}
        title = sess.get("title") or "Assignment help"
        sections = [
            {
                "heading": "What's being asked",
                "body_md": (
                    f"_(LLM unavailable — auto-extracted from assignment row.)_\n\n"
                    f"**Title:** {linked.get('title') or '(none)'}\n\n"
                    f"**Body:**\n\n{linked.get('body') or '(no body captured)'}"
                ),
                "kind": "reference",
            },
            {
                "heading": "How to approach it",
                "body_md": (
                    "Read the body carefully with the kid. Identify the verbs "
                    "(write, list, calculate, explain). Match each to a step. "
                    "Iterate via the prompt box for a real outline."
                ),
                "kind": "step",
            },
        ]
        return {
            "title": title,
            "summary": linked.get("title") or "(see assignment row)",
            "format": "outline",
            "sections": sections,
            "next_steps": [
                "Iterate with a prompt to get a real outline / worked example.",
            ],
            "honest_caveat": (
                "Rule-based skeleton — LLM was unavailable. Use the prompt "
                "box to ask Claude Opus for real help once it's reachable."
            ),
        }

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


def _render_markdown(
    out: dict[str, Any], pack: dict[str, Any], *, kind: str = KIND_REVIEW_PREP,
) -> str:
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

    if kind == KIND_REVIEW_WORK:
        oa = out.get("overall_assessment")
        if oa:
            lines.append(f"_{oa}_")
            lines.append("")
        score = out.get("estimated_score") or {}
        if isinstance(score, dict) and score.get("value") is not None:
            conf = score.get("confidence", "medium")
            lines.append(f"**Estimated score:** {score.get('value')} / {score.get('max', '?')} _(confidence: {conf})_")
            lines.append("")
        verdict_emoji = {
            "correct": "✅", "partially_correct": "🟡",
            "incorrect": "❌", "unclear": "❓",
        }
        for q in out.get("by_question", []):
            v = q.get("verdict") or "unclear"
            emoji = verdict_emoji.get(v, "•")
            lines.append(f"## {emoji} {q.get('ref', '?')} _({v})_")
            lines.append("")
            kid = (q.get("what_kid_did") or "").strip()
            if kid:
                lines.append(f"**Kid wrote:** {kid}")
                lines.append("")
            fb = (q.get("feedback") or "").strip()
            if fb:
                lines.append(fb)
                lines.append("")
            sug = (q.get("suggestion") or "").strip()
            if sug:
                lines.append(f"_Try:_ {sug}")
                lines.append("")
        gs = out.get("general_suggestions") or []
        if gs:
            lines.append("## General suggestions")
            lines.append("")
            for s in gs:
                lines.append(f"- {s}")
            lines.append("")
        lines.append("---")
        lines.append(f"_{out.get('honest_caveat', '')}_")
        return "\n".join(lines)

    if kind == KIND_ASSIGNMENT_HELP:
        if out.get("summary"):
            lines.append(f"_{out['summary']}_")
            lines.append("")
        fmt = out.get("format")
        if fmt:
            lines.append(f"**Format:** {fmt}")
            lines.append("")
        for s in out.get("sections", []):
            heading = s.get("heading", "")
            body = s.get("body_md", "")
            kind_tag = s.get("kind") or ""
            if heading:
                tag_suffix = f"  ·  _{kind_tag}_" if kind_tag else ""
                lines.append(f"## {heading}{tag_suffix}")
                lines.append("")
            if body:
                lines.append(body)
                lines.append("")
        next_steps = out.get("next_steps") or []
        if next_steps:
            lines.append("## Next steps")
            lines.append("")
            for ns in next_steps:
                lines.append(f"- {ns}")
            lines.append("")
        lines.append("---")
        lines.append(f"_{out.get('honest_caveat', '')}_")
        return "\n".join(lines)

    # ── review_prep ────────────────────────────────────────────
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
