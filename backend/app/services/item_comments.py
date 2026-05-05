"""Per-item parent comments — service layer.

Comments are a structured-ish observation log against a specific
veracross_items row. They're designed for LLM aggregation: every
comment carries denormalised child_id and subject (so packs can
filter without joins) plus optional sentiment/topic/tags so the LLM
gets pre-faceted handles for clustering across many comments.

The service exposes the basic CRUD plus an aggregation pack builder
(`build_aggregation_pack`) used by the analysis page and the future
nightly pattern-mining job.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import ItemComment, VeracrossItem
from ..models.item_comments import SENTIMENTS
from .syllabus import normalize_subject

log = logging.getLogger(__name__)


def _to_dict(c: ItemComment) -> dict[str, Any]:
    try:
        tags = json.loads(c.tags_json) if c.tags_json else []
    except Exception:
        tags = []
    return {
        "id": c.id,
        "item_id": c.item_id,
        "child_id": c.child_id,
        "subject": c.subject,
        "body": c.body,
        "sentiment": c.sentiment,
        "topic": c.topic,
        "tags": tags,
        "author": c.author,
        "created_at": c.created_at.isoformat() if c.created_at else None,
        "updated_at": c.updated_at.isoformat() if c.updated_at else None,
    }


async def list_for_item(
    session: AsyncSession, item_id: int,
) -> list[dict[str, Any]]:
    rows = (
        await session.execute(
            select(ItemComment)
            .where(ItemComment.item_id == item_id)
            .order_by(ItemComment.created_at.asc())
        )
    ).scalars().all()
    return [_to_dict(c) for c in rows]


async def list_for_child(
    session: AsyncSession,
    child_id: int,
    *,
    subject: str | None = None,
    days: int | None = None,
    sentiment: str | None = None,
) -> list[dict[str, Any]]:
    """Aggregation read — used by LLM packs to slice over a kid's
    comment history. `days` filters by created_at, `subject` and
    `sentiment` filter on the denormalised columns."""
    q = select(ItemComment).where(ItemComment.child_id == child_id)
    if subject:
        normalised = normalize_subject(subject) or subject
        q = q.where(ItemComment.subject == normalised)
    if sentiment:
        if sentiment not in SENTIMENTS:
            raise ValueError(f"sentiment must be one of {SENTIMENTS}")
        q = q.where(ItemComment.sentiment == sentiment)
    if days is not None and days > 0:
        cutoff = datetime.utcnow() - timedelta(days=days)
        q = q.where(ItemComment.created_at >= cutoff)
    q = q.order_by(ItemComment.created_at.desc())
    rows = (await session.execute(q)).scalars().all()
    return [_to_dict(c) for c in rows]


async def create(
    session: AsyncSession,
    *,
    item_id: int,
    body: str,
    sentiment: str | None = None,
    topic: str | None = None,
    tags: list[str] | None = None,
    author: str = "parent",
) -> dict[str, Any]:
    body = (body or "").strip()
    if not body:
        raise ValueError("comment body is required")
    if sentiment is not None and sentiment not in SENTIMENTS:
        raise ValueError(f"sentiment must be one of {SENTIMENTS} or null")

    item = (
        await session.execute(
            select(VeracrossItem).where(VeracrossItem.id == item_id)
        )
    ).scalar_one_or_none()
    if item is None:
        raise ValueError(f"item {item_id} not found")

    subject = normalize_subject(item.subject) or item.subject

    row = ItemComment(
        item_id=item.id,
        child_id=item.child_id,
        subject=subject,
        body=body,
        sentiment=sentiment,
        topic=(topic or None),
        tags_json=(json.dumps(tags) if tags else None),
        author=author,
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return _to_dict(row)


async def update(
    session: AsyncSession,
    *,
    comment_id: int,
    body: str | None = None,
    sentiment: str | None | type(...) = ...,  # sentinel — None != "no change"
    topic: str | None | type(...) = ...,
    tags: list[str] | None | type(...) = ...,
) -> dict[str, Any]:
    row = (
        await session.execute(
            select(ItemComment).where(ItemComment.id == comment_id)
        )
    ).scalar_one_or_none()
    if row is None:
        raise ValueError(f"comment {comment_id} not found")
    if body is not None:
        b = body.strip()
        if not b:
            raise ValueError("comment body cannot be empty")
        row.body = b
    if sentiment is not ...:
        if sentiment is not None and sentiment not in SENTIMENTS:
            raise ValueError(f"sentiment must be one of {SENTIMENTS} or null")
        row.sentiment = sentiment
    if topic is not ...:
        row.topic = topic
    if tags is not ...:
        row.tags_json = json.dumps(tags) if tags else None
    row.updated_at = datetime.utcnow()
    await session.commit()
    await session.refresh(row)
    return _to_dict(row)


async def delete(session: AsyncSession, comment_id: int) -> None:
    row = (
        await session.execute(
            select(ItemComment).where(ItemComment.id == comment_id)
        )
    ).scalar_one_or_none()
    if row is None:
        raise ValueError(f"comment {comment_id} not found")
    await session.delete(row)
    await session.commit()


async def comment_counts_for_items(
    session: AsyncSession, item_ids: list[int],
) -> dict[int, int]:
    """Return {item_id: count} for the given item ids. Used by the
    list endpoints to surface a 💭N indicator on each row without an
    N+1 query."""
    if not item_ids:
        return {}
    from sqlalchemy import func as _func
    rows = (
        await session.execute(
            select(ItemComment.item_id, _func.count(ItemComment.id))
            .where(ItemComment.item_id.in_(item_ids))
            .group_by(ItemComment.item_id)
        )
    ).all()
    return {iid: int(n) for iid, n in rows}


async def build_aggregation_pack(
    session: AsyncSession,
    *,
    child_id: int,
    days: int = 60,
    subject: str | None = None,
) -> dict[str, Any]:
    """LLM-friendly pack of a kid's comments over a window.

    The LLM reads this and looks for recurring themes ("test anxiety
    flagged on 4 of last 5 Math reviews", "didn't read directions
    appears across subjects"), then returns a clustering result that
    the UI can render. We don't run the LLM here — this function is
    pure data — but the shape is designed to be one Opus call away.
    """
    comments = await list_for_child(
        session, child_id=child_id, days=days, subject=subject,
    )
    # Per-subject and per-sentiment quick stats so the LLM has the
    # contour before it reads the raw text.
    by_subject: dict[str, int] = {}
    by_sentiment: dict[str, int] = {"positive": 0, "neutral": 0, "concern": 0, "unrated": 0}
    by_topic: dict[str, int] = {}
    for c in comments:
        s = c.get("subject") or "(unknown)"
        by_subject[s] = by_subject.get(s, 0) + 1
        sent = c.get("sentiment") or "unrated"
        by_sentiment[sent] = by_sentiment.get(sent, 0) + 1
        topic = c.get("topic")
        if topic:
            by_topic[topic] = by_topic.get(topic, 0) + 1
    return {
        "child_id": child_id,
        "window_days": days,
        "subject_filter": subject,
        "comment_count": len(comments),
        "by_subject": by_subject,
        "by_sentiment": by_sentiment,
        "by_topic": by_topic,
        "comments": comments,
    }
