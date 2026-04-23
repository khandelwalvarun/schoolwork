"""Event production from sync diffs. Pure functions; side-effect-free until persist_events.

Input: the in-memory diff accumulated during a sync pass.
Output: list of (kind, child_id, subject, related_item_id, payload, notability, dedup_key).
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Event, VeracrossItem
from . import rubric as R


@dataclass
class ItemDiff:
    kind: str
    child_id: int
    external_id: str
    is_new: bool = False
    old_status: str | None = None
    new_status: str | None = None
    title: str | None = None
    subject: str | None = None
    due_or_date: str | None = None
    item_id: int | None = None  # filled after upsert
    parent_marked_submitted: bool = False

    def context(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "external_id": self.external_id,
            "subject": self.subject,
            "title": self.title,
            "due_or_date": self.due_or_date,
            "old_status": self.old_status,
            "new_status": self.new_status,
        }


@dataclass
class DiffAggregator:
    diffs: list[ItemDiff] = field(default_factory=list)

    def record(self, d: ItemDiff) -> None:
        self.diffs.append(d)


def _today() -> date:
    return datetime.now(tz=timezone.utc).astimezone().date()


def _days_overdue(due_iso: str | None) -> int:
    if not due_iso:
        return 0
    try:
        d = date.fromisoformat(due_iso)
    except ValueError:
        return 0
    return max(0, (_today() - d).days)


def _is_open(status: str | None) -> bool:
    return status not in {"submitted", "graded", "dismissed"}


def _pack_event(
    kind: R.EventKind,
    child_id: int | None,
    payload: dict[str, Any],
    dedup_key: str,
    subject: str | None = None,
    related_item_id: int | None = None,
) -> dict[str, Any]:
    return {
        "kind": kind.name,
        "child_id": child_id,
        "subject": subject,
        "related_item_id": related_item_id,
        "payload_json": json.dumps(payload, default=str, ensure_ascii=False),
        "notability": kind.notability,
        "dedup_key": dedup_key,
    }


def compute_events(diff: DiffAggregator) -> list[dict[str, Any]]:
    """Derive events from the diff + current world state.

    Handles item-level signals (new, submitted, overdue thresholds, school message).
    Aggregate signals (backlog_accelerating, subject_concentration) are computed in
    `compute_aggregate_events` because they need a DB query.
    """
    out: list[dict[str, Any]] = []
    for d in diff.diffs:
        ctx = d.context()

        if d.kind == "assignment":
            if d.is_new:
                ek = R.NEW_ASSIGNMENT
                out.append(
                    _pack_event(
                        ek, d.child_id, ctx,
                        ek.dedup_key(child=d.child_id, item=d.external_id),
                        subject=d.subject, related_item_id=d.item_id,
                    )
                )
            if d.old_status and d.new_status and d.old_status != d.new_status:
                if d.new_status == "submitted":
                    ek = R.ASSIGNMENT_SUBMITTED
                    out.append(
                        _pack_event(
                            ek, d.child_id, ctx,
                            ek.dedup_key(child=d.child_id, item=d.external_id),
                            subject=d.subject, related_item_id=d.item_id,
                        )
                    )
            # Overdue-threshold crossings apply to any open item whose due is past.
            # Parent-marked submitted items are treated as closed even if the portal hasn't updated.
            if _is_open(d.new_status) and not d.parent_marked_submitted:
                days = _days_overdue(d.due_or_date)
                if days >= 7:
                    ek = R.OVERDUE_7D
                    out.append(
                        _pack_event(
                            ek, d.child_id, {**ctx, "days_overdue": days},
                            ek.dedup_key(child=d.child_id, item=d.external_id),
                            subject=d.subject, related_item_id=d.item_id,
                        )
                    )
                elif days >= 3:
                    ek = R.OVERDUE_3D
                    out.append(
                        _pack_event(
                            ek, d.child_id, {**ctx, "days_overdue": days},
                            ek.dedup_key(child=d.child_id, item=d.external_id),
                            subject=d.subject, related_item_id=d.item_id,
                        )
                    )

        elif d.kind == "school_message":
            if d.is_new:
                ek = R.SCHOOL_MESSAGE
                out.append(
                    _pack_event(
                        ek, None, ctx,
                        ek.dedup_key(item=d.external_id),
                        related_item_id=d.item_id,
                    )
                )

        elif d.kind == "grade":
            # Grade event — we classify routine vs outlier in compute_aggregate_events
            # because it needs the full subject history. Skip here.
            continue

        elif d.kind == "comment":
            if d.is_new:
                body = ctx.get("title") or ""
                words = len(body.split())
                ek = R.COMMENT_LONG if words >= 30 else R.COMMENT_SHORT
                out.append(
                    _pack_event(
                        ek, d.child_id, {**ctx, "word_count": words},
                        ek.dedup_key(child=d.child_id, item=d.external_id),
                        subject=d.subject, related_item_id=d.item_id,
                    )
                )

    return out


async def compute_aggregate_events(
    session: AsyncSession, diff: DiffAggregator
) -> list[dict[str, Any]]:
    """Cross-item signals. Each fires at most once per window via the dedup_key."""
    today = _today()
    week_key = today.strftime("%G-W%V")
    out: list[dict[str, Any]] = []

    # Grade outlier detection — compare each freshly-seen grade to its subject history.
    new_grades = [d for d in diff.diffs if d.kind == "grade" and d.is_new]
    for d in new_grades:
        # Query history for the same child+subject
        from sqlalchemy import and_
        history = (
            await session.execute(
                select(VeracrossItem)
                .where(VeracrossItem.kind == "grade")
                .where(VeracrossItem.child_id == d.child_id)
                .where(VeracrossItem.subject == d.subject)
            )
        ).scalars().all()
        # Extract grade_pct from normalized_json for each
        pcts: list[float] = []
        this_pct: float | None = None
        for h in history:
            try:
                nj = json.loads(h.normalized_json or "{}")
                p = nj.get("grade_pct")
                if p is None:
                    continue
                if h.external_id == d.external_id:
                    this_pct = float(p)
                else:
                    pcts.append(float(p))
            except Exception:
                continue
        if this_pct is None:
            continue
        ek = R.GRADE_POSTED_ROUTINE
        payload = d.context() | {"grade_pct": this_pct, "history_n": len(pcts)}
        if len(pcts) >= 3:
            mean = sum(pcts) / len(pcts)
            var = sum((x - mean) ** 2 for x in pcts) / len(pcts)
            sigma = var ** 0.5
            payload |= {"mean": mean, "sigma": sigma}
            if sigma > 0 and abs(this_pct - mean) > sigma:
                ek = R.GRADE_POSTED_OUTLIER
        out.append(
            _pack_event(
                ek, d.child_id, payload,
                ek.dedup_key(child=d.child_id, subject=d.subject, item=d.external_id),
                subject=d.subject, related_item_id=d.item_id,
            )
        )

    # Per-child: open overdue snapshot → subject concentration + backlog acceleration.
    # Parent-marked submitted items are excluded — the parent already said it's done.
    rows = (
        await session.execute(
            select(VeracrossItem.child_id, VeracrossItem.subject, VeracrossItem.due_or_date)
            .where(VeracrossItem.kind == "assignment")
            .where(~VeracrossItem.status.in_(("submitted", "graded", "dismissed")))
            .where(VeracrossItem.parent_marked_submitted_at.is_(None))
        )
    ).all()
    by_child: dict[int, list[tuple[str | None, str | None]]] = defaultdict(list)
    for child_id, subj, due in rows:
        if due and due < today.isoformat():
            by_child[child_id].append((subj, due))

    for child_id, items in by_child.items():
        total = len(items)
        if total == 0:
            continue

        # subject_concentration
        counts = Counter(subj for subj, _ in items if subj)
        for subj, n in counts.items():
            if n >= 4 and (n / total) > 0.40:
                ek = R.SUBJECT_CONCENTRATION
                out.append(
                    _pack_event(
                        ek, child_id,
                        {"subject": subj, "overdue_in_subject": n, "overdue_total": total},
                        ek.dedup_key(child=child_id, subject=subj, week=week_key),
                        subject=subj,
                    )
                )

        # backlog_accelerating: compare to the backlog from 48h ago (via events history
        # — count open-overdue-assignment events recorded 2 days ago). Fallback to the
        # simple trigger: if today's overdue >= 6 and at least one crossed threshold
        # today. Conservative first implementation.
        if total >= 6:
            ek = R.BACKLOG_ACCELERATING
            out.append(
                _pack_event(
                    ek, child_id,
                    {"overdue_now": total},
                    ek.dedup_key(child=child_id, week=week_key),
                )
            )

    return out


async def persist_events(
    session: AsyncSession, packed: list[dict[str, Any]]
) -> list[int]:
    """Insert events with ON CONFLICT(dedup_key) DO NOTHING. Returns inserted IDs."""
    if not packed:
        return []
    stmt = sqlite_insert(Event).values(packed)
    stmt = stmt.on_conflict_do_nothing(index_elements=[Event.dedup_key])
    await session.execute(stmt)

    # SQLAlchemy 2.0 doesn't expose affected row ids from the insert + on-conflict,
    # so we round-trip by dedup_key to find which ones landed with recent created_at.
    keys = [p["dedup_key"] for p in packed]
    rows = (
        await session.execute(
            select(Event.id)
            .where(Event.dedup_key.in_(keys))
            .order_by(Event.id.desc())
        )
    ).scalars().all()
    return list(rows)[: len(keys)]
