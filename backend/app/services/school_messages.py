"""School-message dedup + LLM 1-sentence summary.

Phase 22, per the user's spec: "sometimes both kids receive identical
announcements; in case there are two announcements, one for each kid,
then just show one and tag it for both. Summarize the email in one
sentence with any relevant link using local ollama llm to summarize.
Clicking on the row should bring a drop down that does this."

Implementation choices:

  Dedup key
    Normalized title (lowercased, whitespace-collapsed) is the grouping
    key. Date isn't part of the key — same announcement may surface on
    different scrape days. Within a group we keep all member rows so
    the UI can show "tagged for: Tejas, Samarth".

  Summary persistence
    Generated on-demand via /api/school-messages/{group_id}/summarize.
    The result is cached on `llm_summary` + `llm_summary_url` of every
    row in the group, so subsequent dedup queries return the cached
    summary without another LLM call.

  Summary content
    A single sentence (≤ 200 chars) extracted by the local Ollama LLM
    from whichever member has the richest text (longest body or title_en).
    The first http(s) URL in the body is also extracted and stored
    separately so the UI can render it as a clickable link.

  Honest framing
    The summary is *advisory* — the parent can always click through to
    the full title or open the original Veracross message. We never
    drop content; dedup just groups view rows.
"""
from __future__ import annotations

import logging
import re
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..llm.client import LLMClient
from ..models import Child, VeracrossItem


log = logging.getLogger(__name__)

URL_RE = re.compile(r"https?://\S+")
WS_RE = re.compile(r"\s+")


def _normalize_title(title: str | None) -> str:
    if not title:
        return ""
    s = title.strip().lower()
    s = WS_RE.sub(" ", s)
    return s


def _first_url(text: str | None) -> str | None:
    if not text:
        return None
    m = URL_RE.search(text)
    if m is None:
        return None
    return m.group(0).rstrip(").,;:")


def _best_body(rows: list[VeracrossItem]) -> str:
    """Pick the richest text source across the group — prefer body,
    fall back to notes_en or title_en or title."""
    pool: list[str] = []
    for r in rows:
        for cand in (r.body, r.notes_en, r.title_en, r.title):
            if cand and cand.strip():
                pool.append(cand.strip())
                break  # one per row max
    pool.sort(key=len, reverse=True)
    return pool[0] if pool else ""


SUMMARY_SYSTEM = (
    "You are a concise school-message summarizer for a busy parent. "
    "Return a SINGLE sentence (under 200 characters) capturing the "
    "essential ask, deadline, or info from the message. Drop greetings, "
    "signatures, and boilerplate. Do not start with 'This message is' "
    "or 'The school is announcing'. If a date or fee or deadline is "
    "mentioned, include it verbatim. Do not include the URL — that's "
    "surfaced separately. Do not invent details."
)


async def _llm_summarize(text: str) -> str | None:
    """Call the configured local LLM (Ollama by default) for a 1-sentence
    summary. Returns None on failure — caller should fall back."""
    if not text or not text.strip():
        return None
    client = LLMClient()
    if not client.enabled():
        return None
    try:
        resp = await client.complete(
            purpose="school_message_summary",
            system=SUMMARY_SYSTEM,
            prompt=text,
            max_tokens=120,
        )
    except Exception as e:
        log.warning("school_message_summary LLM call failed: %s", e)
        return None
    out = (resp.text or "").strip()
    # Strip leading/trailing quotes the LLM sometimes adds.
    if out and out[0] in ('"', "'") and out[-1] in ('"', "'"):
        out = out[1:-1].strip()
    # Hard cap at 240 chars in case the LLM ignored the limit.
    if len(out) > 240:
        out = out[:237].rstrip() + "…"
    return out or None


def _group_id(rows: list[VeracrossItem]) -> str:
    """Stable group id derived from the smallest row id in the group —
    survives across calls so the API can address a specific group."""
    return f"grp{min(r.id for r in rows)}"


def _row_to_dict(r: VeracrossItem, child_lookup: dict[int, Child]) -> dict[str, Any]:
    c = child_lookup.get(r.child_id) if r.child_id else None
    return {
        "id": r.id,
        "child_id": r.child_id,
        "child_name": c.display_name if c else None,
        "title": r.title,
        "title_en": r.title_en,
        "body": r.body,
        "due_or_date": r.due_or_date,
        "first_seen_at": r.first_seen_at.isoformat() if r.first_seen_at else None,
    }


async def list_grouped_messages(
    session: AsyncSession,
    *,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Return school messages collapsed by normalized title. Each group
    carries: group_id, normalized_title, latest_seen, kids (list of
    {child_id, display_name}), members (raw rows), llm_summary +
    llm_summary_url cached on the latest member."""
    rows = (
        await session.execute(
            select(VeracrossItem)
            .where(VeracrossItem.kind == "school_message")
            .order_by(VeracrossItem.first_seen_at.desc())
        )
    ).scalars().all()

    children = (await session.execute(select(Child))).scalars().all()
    child_lookup: dict[int, Child] = {c.id: c for c in children}

    groups: dict[str, list[VeracrossItem]] = {}
    for r in rows:
        key = _normalize_title(r.title)
        if not key:
            key = f"raw:{r.id}"  # singleton group for unparseable
        groups.setdefault(key, []).append(r)

    out: list[dict[str, Any]] = []
    for key, members in groups.items():
        members.sort(key=lambda m: m.first_seen_at or m.id, reverse=True)
        latest = members[0]
        kids: list[dict[str, Any]] = []
        seen_kids: set[int] = set()
        for m in members:
            if m.child_id is None or m.child_id in seen_kids:
                continue
            seen_kids.add(m.child_id)
            c = child_lookup.get(m.child_id)
            kids.append({
                "child_id": m.child_id,
                "display_name": c.display_name if c else None,
            })
        # Summary cache lives on any member that's already been
        # summarised — copy from the freshest.
        cached = next(
            (m for m in members if m.llm_summary), None,
        )
        out.append({
            "group_id": _group_id(members),
            "normalized_title": key,
            "title": latest.title,
            "title_en": latest.title_en,
            "latest_seen": latest.first_seen_at.isoformat() if latest.first_seen_at else None,
            "latest_date": latest.due_or_date,
            "member_count": len(members),
            "kids": kids,
            "llm_summary": cached.llm_summary if cached else None,
            "llm_summary_url": cached.llm_summary_url if cached else None,
            "members": [_row_to_dict(m, child_lookup) for m in members],
        })
    out.sort(key=lambda g: g["latest_seen"] or "", reverse=True)
    return out[:limit]


async def summarize_group(
    session: AsyncSession,
    group_id: str,
) -> dict[str, Any]:
    """Compute (or refresh) the 1-sentence summary for a dedup group and
    cache it onto every member row's llm_summary / llm_summary_url
    fields. Returns the new summary + URL."""
    if not group_id.startswith("grp"):
        raise ValueError(f"bad group_id {group_id!r}")
    try:
        anchor_id = int(group_id[3:])
    except ValueError as e:
        raise ValueError(f"bad group_id {group_id!r}") from e

    anchor = (
        await session.execute(
            select(VeracrossItem).where(VeracrossItem.id == anchor_id)
        )
    ).scalar_one_or_none()
    if anchor is None or anchor.kind != "school_message":
        raise ValueError(f"group {group_id} not found")

    key = _normalize_title(anchor.title)
    if not key:
        members = [anchor]
    else:
        rows = (
            await session.execute(
                select(VeracrossItem)
                .where(VeracrossItem.kind == "school_message")
            )
        ).scalars().all()
        members = [r for r in rows if _normalize_title(r.title) == key]
    if not members:
        raise ValueError(f"group {group_id} empty")

    text = _best_body(members)
    if not text:
        # Use the title only — at least we still get a summary.
        text = anchor.title or ""

    summary = await _llm_summarize(text)
    url = _first_url(text)

    # Fall back to a clipped version of the body if the LLM was unavailable.
    if summary is None:
        clip = WS_RE.sub(" ", text).strip()
        if len(clip) > 220:
            clip = clip[:217].rstrip() + "…"
        summary = clip or anchor.title or ""

    for m in members:
        m.llm_summary = summary
        m.llm_summary_url = url
    await session.commit()

    return {
        "group_id": group_id,
        "summary": summary,
        "url": url,
        "members": len(members),
        "llm_used": summary is not None and summary != (anchor.title or ""),
    }
