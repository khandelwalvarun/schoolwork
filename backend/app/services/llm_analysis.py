"""Free-form LLM analysis over the parent-cockpit data.

The parent asks a question — "What is Tejas struggling with this
month?" / "Where is Samarth's writing improving?" / "Anything I
should worry about before next week's PTM?" — and Claude Opus pulls
relevant context from the existing tables and answers with structured
findings + supporting evidence + caveats.

Scope (per call):
  - child_id (optional) — narrows to one kid; otherwise spans all
  - scope_days — how far back to pull data (default 30)

Pack (deterministic, built fresh each call):
  - children + class info
  - recent grades (with subject + pct + graded_date + body)
  - recent assignments due in the window (open + closed)
  - recent comments
  - recent school messages
  - last few sync_runs (so the LLM knows how fresh the data is)
  - shaky topics
  - off-trend grade anomalies
  - pattern flags (lateness / repeated_attempt / weekend_cramming)
  - mindspark progress (sessions + topics)

Output schema (strict JSON):
  {
    "headline": "<one-sentence direct answer>",
    "findings": [
      {
        "title": "<short title>",
        "evidence": "<2-3 sentences with row-level detail>",
        "confidence": "high | medium | low",
        "scope": "child_name | both | unknown"
      },
      ...
    ],
    "pointers": [
      "<concrete suggestion or follow-up>",
      ...
    ],
    "caveats": [
      "<honest limitation>",
      ...
    ],
    "raw_data_used": {
      "grades_count": int,
      "assignments_count": int,
      "comments_count": int,
      "messages_count": int,
      "scope_days": int,
      "children": ["Tejas", "Samarth"]
    }
  }
"""
from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..llm.client import LLMClient
from ..models import (
    Child, LLMAnalysis, MindsparkSession as MS, MindsparkTopicProgress as MTP,
    PatternState, SyncRun, VeracrossItem,
)
from .anomaly import detect_anomalies_for_child
from .grade_match import _parse_loose_date
from .shaky_topics import shaky_for_child
from .syllabus import normalize_subject


log = logging.getLogger(__name__)

ANALYSIS_LLM_MODEL_DEFAULT = "claude-opus-4-5"
MAX_QUERY_LEN = 1000


# ───────────────────────── public API ─────────────────────────

async def run_analysis(
    session: AsyncSession,
    *,
    query: str,
    child_id: int | None = None,
    scope_days: int = 30,
    use_llm: bool = True,
) -> dict[str, Any]:
    """Run one analysis. Always inserts an LLMAnalysis row (even on
    failure) so the parent's history is complete."""
    q = (query or "").strip()
    if not q:
        raise ValueError("query is required")
    if len(q) > MAX_QUERY_LEN:
        raise ValueError(f"query is longer than {MAX_QUERY_LEN} chars")
    scope_days = max(1, min(int(scope_days or 30), 365))

    pack = await _build_pack(session, child_id=child_id, scope_days=scope_days)

    out_dict: dict[str, Any] | None = None
    llm_used = False
    llm_model = None
    in_t = out_t = None
    err: str | None = None
    started = time.monotonic()
    if use_llm:
        try:
            out_dict, llm_used, llm_model, in_t, out_t = await _claude_synthesize(
                pack=pack, query=q,
            )
        except Exception as e:
            err = repr(e)[:500]
            log.warning("llm_analysis call failed: %s", e)
    duration_ms = int((time.monotonic() - started) * 1000)
    if out_dict is None:
        out_dict = _rule_skeleton(pack, query=q)
    md = _render_markdown(out_dict, query=q, pack=pack)

    row = LLMAnalysis(
        child_id=child_id,
        query=q,
        scope_days=scope_days,
        output_md=md,
        output_json=json.dumps(out_dict, ensure_ascii=False, default=str),
        llm_used=llm_used,
        llm_model=llm_model,
        llm_input_tokens=in_t,
        llm_output_tokens=out_t,
        duration_ms=duration_ms,
        error=err,
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return _to_dict(row)


async def list_analyses(
    session: AsyncSession,
    *,
    child_id: int | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    q = select(LLMAnalysis).order_by(desc(LLMAnalysis.created_at))
    if child_id is not None:
        q = q.where(LLMAnalysis.child_id == child_id)
    q = q.limit(limit)
    rows = (await session.execute(q)).scalars().all()
    return [_to_dict(r, light=True) for r in rows]


async def get_analysis(session: AsyncSession, analysis_id: int) -> dict[str, Any]:
    row = (
        await session.execute(
            select(LLMAnalysis).where(LLMAnalysis.id == analysis_id)
        )
    ).scalar_one_or_none()
    if row is None:
        raise ValueError(f"analysis {analysis_id} not found")
    return _to_dict(row)


# ───────────────────────── pack builder ─────────────────────────

async def _build_pack(
    session: AsyncSession,
    *,
    child_id: int | None,
    scope_days: int,
) -> dict[str, Any]:
    today = datetime.now(tz=timezone.utc).date()
    since = today - timedelta(days=scope_days)

    children_q = select(Child).order_by(Child.id)
    if child_id is not None:
        children_q = children_q.where(Child.id == child_id)
    children = list((await session.execute(children_q)).scalars().all())
    if not children:
        return {"children": [], "today": today.isoformat(), "scope_days": scope_days}

    items_q = (
        select(VeracrossItem)
        .where(VeracrossItem.child_id.in_([c.id for c in children]))
        .order_by(desc(VeracrossItem.due_or_date))
    )
    items = (await session.execute(items_q)).scalars().all()

    # Slice items by date scope + kind buckets.
    grades: list[dict[str, Any]] = []
    assignments: list[dict[str, Any]] = []
    comments: list[dict[str, Any]] = []
    messages: list[dict[str, Any]] = []
    for it in items:
        d = _parse_loose_date(it.due_or_date)
        if d is None or d < since or d > today + timedelta(days=14):
            # Allow upcoming assignments up to 14 days ahead.
            if not (it.kind == "assignment" and d and today <= d <= today + timedelta(days=14)):
                continue
        try:
            normalized = json.loads(it.normalized_json or "{}")
        except Exception:
            normalized = {}
        common = {
            "id": it.id,
            "child_id": it.child_id,
            "subject": normalize_subject(it.subject) or it.subject,
            "title": it.title,
            "title_en": it.title_en,
            "due_or_date": it.due_or_date,
            "status": it.status,
        }
        if it.kind == "grade":
            pct = normalized.get("grade_pct")
            if pct is None:
                continue
            grades.append({**common, "pct": float(pct),
                           "score_text": normalized.get("score_text"),
                           "anomaly_explanation": it.llm_summary})
        elif it.kind == "assignment":
            assignments.append({**common,
                                "body": (it.body or "")[:600],
                                "the_ask": it.llm_summary,
                                "parent_status": it.parent_status})
        elif it.kind == "comment":
            comments.append({**common, "body": (it.body or "")[:600]})
        elif it.kind in ("message", "school_message"):
            messages.append({**common, "body": (it.body or "")[:400]})

    # Cross-cutting signals.
    pattern_states: dict[int, dict[str, Any]] = {}
    cur_month = today.strftime("%Y-%m")
    pq = (
        await session.execute(
            select(PatternState)
            .where(PatternState.child_id.in_([c.id for c in children]))
            .where(PatternState.month == cur_month)
        )
    ).scalars().all()
    for p in pq:
        pattern_states[p.child_id] = {
            "lateness": bool(p.lateness),
            "repeated_attempt": bool(p.repeated_attempt),
            "weekend_cramming": bool(p.weekend_cramming),
        }

    shaky_per_kid: dict[int, list[dict[str, Any]]] = {}
    anomalies_per_kid: dict[int, list[dict[str, Any]]] = {}
    for c in children:
        try:
            shaky_per_kid[c.id] = await shaky_for_child(session, c, limit=10)
        except Exception:
            shaky_per_kid[c.id] = []
        try:
            anomalies_per_kid[c.id] = await detect_anomalies_for_child(session, c.id)
        except Exception:
            anomalies_per_kid[c.id] = []

    # Mindspark — light slice.
    mindspark_per_kid: dict[int, dict[str, Any]] = {}
    for c in children:
        m_topics = (
            await session.execute(
                select(MTP)
                .where(MTP.child_id == c.id)
                .order_by(desc(MTP.last_activity_at).nulls_last())
                .limit(8)
            )
        ).scalars().all()
        m_sessions = (
            await session.execute(
                select(MS)
                .where(MS.child_id == c.id)
                .order_by(desc(MS.started_at))
                .limit(5)
            )
        ).scalars().all()
        if m_topics or m_sessions:
            mindspark_per_kid[c.id] = {
                "topics": [
                    {
                        "subject": t.subject,
                        "topic_name": t.topic_name,
                        "accuracy_pct": t.accuracy_pct,
                        "mastery_level": t.mastery_level,
                    }
                    for t in m_topics
                ],
                "sessions": [
                    {
                        "subject": s.subject,
                        "topic_name": s.topic_name,
                        "started_at": s.started_at.isoformat() if s.started_at else None,
                        "questions_total": s.questions_total,
                        "accuracy_pct": s.accuracy_pct,
                    }
                    for s in m_sessions
                ],
            }

    # Last 3 sync_runs so the LLM can reason about freshness.
    last_runs = (
        await session.execute(
            select(SyncRun).order_by(desc(SyncRun.started_at)).limit(3)
        )
    ).scalars().all()
    sync_freshness = [
        {
            "trigger": r.trigger,
            "started_at": r.started_at.isoformat() if r.started_at else None,
            "status": r.status,
            "items_new": r.items_new,
            "items_updated": r.items_updated,
        }
        for r in last_runs
    ]

    return {
        "today": today.isoformat(),
        "scope_days": scope_days,
        "since": since.isoformat(),
        "children": [
            {
                "id": c.id,
                "name": c.display_name,
                "class_level": c.class_level,
                "class_section": c.class_section,
                "pattern_flags_this_month": pattern_states.get(c.id, {}),
                "shaky_topics": shaky_per_kid.get(c.id, []),
                "off_trend_grades": anomalies_per_kid.get(c.id, []),
                "mindspark": mindspark_per_kid.get(c.id, {}),
            }
            for c in children
        ],
        "grades": grades,
        "assignments": assignments,
        "comments": comments,
        "messages": messages,
        "sync_runs": sync_freshness,
    }


# ───────────────────────── LLM call + validation ─────────────────────────

SYSTEM_PROMPT = """You are an analyst over a parent's child-tracking dashboard data. The parent asks an open question; you answer with structured findings backed by the data they pasted.

You receive:
  - DATA PACK (JSON) — children, recent grades / assignments / comments / messages, pattern flags, shaky topics, off-trend grade anomalies, mindspark progress, sync_runs (data freshness)
  - QUERY — the parent's free-form question

OUTPUT — strict JSON only, matching:

{
  "headline": "<one sentence direct answer to the query>",
  "findings": [
    {
      "title": "<short title>",
      "evidence": "<2-3 sentences with concrete row-level detail (subject, title, score, date, body excerpt)>",
      "confidence": "high | medium | low",
      "scope": "<child name | both | school-wide>"
    },
    ...
  ],   // 2-6 items
  "pointers": [
    "<concrete suggestion or follow-up — e.g. 'practice fraction-decimal conversion before May 5 review'>",
    "..."
  ],   // 0-4 items
  "caveats": [
    "<honest limitation — e.g. 'sample is only 4 grades — direction is suggestive, not significant'>",
    "..."
  ],   // 0-3 items
  "raw_data_used": {
    "grades_count": <int>,
    "assignments_count": <int>,
    "comments_count": <int>,
    "messages_count": <int>,
    "scope_days": <int>,
    "children": ["<name>", ...]
  }
}

RULES:
- The headline is a direct answer; don't dodge or redirect.
- Every finding cites concrete rows from the pack (subject + title + value + date when relevant).
- Use the pattern_flags_this_month, shaky_topics, off_trend_grades fields — they're pre-computed signals; surface them when relevant rather than rederiving from raw grades.
- Min-sample suppression: if a kid has ≤2 grades in the window, mention it in caveats and lower confidence to "low".
- No comparison to siblings unless the parent's query asks for it.
- No behavioural attribution ("the kid is lazy" / "lacks focus" — forbidden). Stick to observable patterns.
- For non-Latin subject names (Hindi / Sanskrit), include both the original script and an English transliteration when relevant.
- caveats should be 1-3 honest limitations (small sample / data freshness / ambiguity in the query).
- raw_data_used is REQUIRED and reflects the actual counts visible in the pack.
- Return ONLY the JSON object. No prose outside braces. No code fences."""


async def _claude_synthesize(
    pack: dict[str, Any], query: str,
) -> tuple[dict[str, Any] | None, bool, str | None, int | None, int | None]:
    from ..config import get_settings
    settings = get_settings()
    client = LLMClient()
    if not client.enabled():
        return None, False, None, None, None
    model = (
        getattr(settings, "analysis_llm_model", "")
        or getattr(settings, "practice_llm_model", "")
        or ANALYSIS_LLM_MODEL_DEFAULT
    )
    pack_json = json.dumps(pack, default=str, ensure_ascii=False, indent=2)
    prompt = (
        f"QUERY:\n{query}\n\n"
        f"DATA PACK:\n```json\n{pack_json}\n```\n\nGenerate the analysis."
    )
    try:
        resp = await client.complete(
            purpose="llm_analysis",
            system=SYSTEM_PROMPT,
            prompt=prompt,
            model=model,
            max_tokens=3500,
        )
    except Exception as e:
        log.warning("llm_analysis: LLM call failed: %s", e)
        return None, False, model, None, None
    text = (resp.text or "").strip()
    if text.startswith("```"):
        parts = text.split("```", 2)
        if len(parts) >= 2:
            text = parts[1]
            if text.lstrip().startswith("json"):
                text = text.split("\n", 1)[1] if "\n" in text else text
    try:
        out = json.loads(text)
    except Exception as e:
        log.warning("llm_analysis: bad JSON: %s; raw=%r", e, text[:300])
        return None, False, resp.model, resp.input_tokens, resp.output_tokens
    err = _validate(out)
    if err:
        log.warning("llm_analysis: validation failed: %s", err)
        return None, False, resp.model, resp.input_tokens, resp.output_tokens
    return out, True, resp.model, resp.input_tokens, resp.output_tokens


def _validate(out: dict[str, Any]) -> str | None:
    if not isinstance(out, dict):
        return "output is not an object"
    if not isinstance(out.get("headline"), str) or not out["headline"].strip():
        return "headline missing"
    findings = out.get("findings")
    if not isinstance(findings, list) or not findings:
        return "findings must be a non-empty list"
    for i, f in enumerate(findings):
        if not isinstance(f, dict):
            return f"findings[{i}]: not an object"
        for k in ("title", "evidence"):
            if not isinstance(f.get(k), str) or not f[k].strip():
                return f"findings[{i}]: {k} missing"
    if not isinstance(out.get("raw_data_used"), dict):
        return "raw_data_used must be an object"
    return None


def _rule_skeleton(pack: dict[str, Any], query: str) -> dict[str, Any]:
    """Mechanical fallback when the LLM is unreachable. Echoes back
    counts so the parent at least sees the data we'd have used."""
    children_names = [c["name"] for c in pack.get("children", [])]
    return {
        "headline": "LLM unavailable — here's what data is on file for the question.",
        "findings": [
            {
                "title": "Pack summary",
                "evidence": (
                    f"{len(pack.get('grades', []))} grades, "
                    f"{len(pack.get('assignments', []))} assignments, "
                    f"{len(pack.get('comments', []))} comments, "
                    f"{len(pack.get('messages', []))} messages "
                    f"in the last {pack.get('scope_days', 30)} days "
                    f"across {len(children_names)} kid(s)."
                ),
                "confidence": "low",
                "scope": ", ".join(children_names) or "—",
            }
        ],
        "pointers": [
            "Re-run when the LLM backend is reachable.",
        ],
        "caveats": [
            "This is a rule-based skeleton — no LLM analysis performed.",
        ],
        "raw_data_used": {
            "grades_count": len(pack.get("grades", [])),
            "assignments_count": len(pack.get("assignments", [])),
            "comments_count": len(pack.get("comments", [])),
            "messages_count": len(pack.get("messages", [])),
            "scope_days": pack.get("scope_days", 30),
            "children": children_names,
        },
    }


def _render_markdown(
    out: dict[str, Any], *, query: str, pack: dict[str, Any],
) -> str:
    lines: list[str] = []
    lines.append("# " + (out.get("headline") or "Analysis"))
    lines.append("")
    lines.append(f"_Query: {query}_")
    lines.append("")
    findings = out.get("findings") or []
    for f in findings:
        lines.append(f"## {f.get('title', '')}")
        scope = f.get("scope")
        conf = f.get("confidence")
        if scope or conf:
            lines.append(
                f"<sub>{' · '.join(filter(None, [scope, conf]))}</sub>"
            )
        lines.append("")
        lines.append(f.get("evidence", ""))
        lines.append("")
    pointers = out.get("pointers") or []
    if pointers:
        lines.append("## Suggested next steps")
        lines.append("")
        for p in pointers:
            lines.append(f"- {p}")
        lines.append("")
    caveats = out.get("caveats") or []
    if caveats:
        lines.append("## Caveats")
        lines.append("")
        for c in caveats:
            lines.append(f"- {c}")
        lines.append("")
    used = out.get("raw_data_used") or {}
    lines.append("---")
    lines.append(
        f"_{used.get('grades_count', 0)} grades · "
        f"{used.get('assignments_count', 0)} assignments · "
        f"{used.get('comments_count', 0)} comments · "
        f"{used.get('messages_count', 0)} messages over "
        f"{used.get('scope_days', 30)} days_"
    )
    return "\n".join(lines)


def _to_dict(row: LLMAnalysis, light: bool = False) -> dict[str, Any]:
    out_json: Any = None
    if not light and row.output_json:
        try:
            out_json = json.loads(row.output_json)
        except Exception:
            out_json = None
    base = {
        "id": row.id,
        "child_id": row.child_id,
        "query": row.query,
        "scope_days": row.scope_days,
        "llm_used": bool(row.llm_used),
        "llm_model": row.llm_model,
        "duration_ms": row.duration_ms,
        "error": row.error,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }
    if light:
        return base
    return {
        **base,
        "output_md": row.output_md,
        "output_json": out_json,
        "llm_input_tokens": row.llm_input_tokens,
        "llm_output_tokens": row.llm_output_tokens,
    }
