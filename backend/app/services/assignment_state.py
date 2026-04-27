"""Parent-side state tracking for assignments — the 'professional' layer.

Effective-status precedence rule (top wins):
    graded  (portal_status)
    submitted  (portal_status OR parent_status)
    done_at_home  (parent_status)
    in_progress  (parent_status)
    needs_help  (parent_status)
    blocked  (parent_status)
    skipped  (parent_status)
    overdue  (portal_status)
    pending  (portal default)
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import AssignmentStatusHistory, VeracrossItem


# Canonical parent-status values. `None` / empty = untracked (falls through to portal).
PARENT_STATUSES: tuple[str, ...] = (
    "in_progress",
    "done_at_home",
    "submitted",
    "needs_help",
    "blocked",
    "skipped",
)

# Fixed tag vocabulary (UI shows them as toggle chips).
FIXED_TAGS: tuple[str, ...] = (
    "needs-printing",
    "needs-parent-help",
    "needs-teacher-help",
    "missing-materials",
    "tomorrow",
    "weekend",
    "revision",
    "re-do",
)

# Portal statuses that represent terminal states.
_TERMINAL_PORTAL = {"graded", "dismissed"}
_SUBMITTED_PORTAL = {"submitted"}
_TERMINAL_PARENT = {"submitted", "done_at_home", "skipped", "blocked"}


def effective_status(portal: str | None, parent: str | None) -> str:
    """Apply the precedence rule above and return a single effective status."""
    p = (portal or "").strip() or None
    m = (parent or "").strip() or None
    if p == "graded":
        return "graded"
    if m == "submitted" or p in _SUBMITTED_PORTAL:
        return "submitted"
    if m == "done_at_home":
        return "done_at_home"
    if m == "in_progress":
        return "in_progress"
    if m == "needs_help":
        return "needs_help"
    if m == "blocked":
        return "blocked"
    if m == "skipped":
        return "skipped"
    if p == "overdue":
        return "overdue"
    if p == "dismissed":
        return "dismissed"
    return p or "pending"


def should_suppress_overdue_events(parent_status: str | None) -> bool:
    """Notability engine uses this — overdue threshold events are skipped
    whenever the parent says the item is effectively closed on their side."""
    return (parent_status or "").strip() in _TERMINAL_PARENT


def parse_tags(tags_json: str | None) -> list[str]:
    if not tags_json:
        return []
    try:
        val = json.loads(tags_json)
        if not isinstance(val, list):
            return []
        return [t for t in val if isinstance(t, str)]
    except Exception:
        return []


def _normalize_tags(raw: Any) -> list[str]:
    """Take the patch input for tags and produce a sanitized, deduped list
    from the fixed vocabulary only."""
    if raw is None:
        return []
    if isinstance(raw, str):
        raw = [raw]
    if not isinstance(raw, list):
        return []
    out: list[str] = []
    seen: set[str] = set()
    for t in raw:
        if not isinstance(t, str):
            continue
        t = t.strip().lower().replace(" ", "-")
        if t in FIXED_TAGS and t not in seen:
            out.append(t)
            seen.add(t)
    return out


async def update_assignment_state(
    session: AsyncSession,
    item_id: int,
    patch: dict[str, Any],
    actor: str | None = None,
) -> dict[str, Any] | None:
    """Apply a partial update of parent-state fields to an assignment,
    writing one audit-log row per changed field. Returns the updated item
    dict or None if the id doesn't exist."""
    item = (
        await session.execute(select(VeracrossItem).where(VeracrossItem.id == item_id))
    ).scalar_one_or_none()
    if item is None:
        return None
    # Most fields are assignment-only by the parent-status semantics we
    # defined. The "worth a chat" flag, however, applies to any item the
    # parent might raise at PTM (a grade, a comment, a school message)
    # so we allow the patch through for non-assignments BUT only if the
    # patch is restricted to flag-only keys; otherwise reject.
    flag_only_keys = {"discuss_with_teacher", "discuss_with_teacher_note", "note", "actor"}
    if item.kind != "assignment" and not (set(patch.keys()) <= flag_only_keys):
        return None

    now = datetime.now(tz=timezone.utc)
    changes: list[AssignmentStatusHistory] = []

    def _record(field: str, old: Any, new: Any) -> None:
        changes.append(
            AssignmentStatusHistory(
                item_id=item_id,
                field=field,
                old_value=None if old is None else str(old),
                new_value=None if new is None else str(new),
                source="parent",
                actor=actor,
                note=patch.get("note") if field == "parent_status" else None,
                created_at=now,
            )
        )

    # parent_status
    if "parent_status" in patch:
        new_ps = patch["parent_status"]
        if new_ps is not None and new_ps != "" and new_ps not in PARENT_STATUSES:
            raise ValueError(f"invalid parent_status: {new_ps!r}")
        new_ps = new_ps if (new_ps or "") else None
        if new_ps != item.parent_status:
            _record("parent_status", item.parent_status, new_ps)
            item.parent_status = new_ps
            # Legacy flag: keep parent_marked_submitted_at in sync so old code
            # that reads it continues to work.
            if new_ps == "submitted":
                item.parent_marked_submitted_at = now
            elif new_ps is None and item.parent_marked_submitted_at is not None:
                item.parent_marked_submitted_at = None

    # priority
    if "priority" in patch:
        new_pr = int(patch["priority"]) if patch["priority"] is not None else 0
        new_pr = max(0, min(3, new_pr))
        if new_pr != item.priority:
            _record("priority", item.priority, new_pr)
            item.priority = new_pr

    # snooze_until
    if "snooze_until" in patch:
        raw = patch["snooze_until"]
        new_snooze = (raw or None) if isinstance(raw, (str, type(None))) else None
        if new_snooze != item.snooze_until:
            _record("snooze_until", item.snooze_until, new_snooze)
            item.snooze_until = new_snooze

    # status_notes
    if "status_notes" in patch:
        new_notes = patch["status_notes"] or None
        if new_notes != item.status_notes:
            _record("status_notes", item.status_notes, new_notes)
            item.status_notes = new_notes

    # tags
    if "tags" in patch:
        new_tags = _normalize_tags(patch["tags"])
        current_tags = parse_tags(item.tags_json)
        if new_tags != current_tags:
            _record("tags", json.dumps(current_tags), json.dumps(new_tags))
            item.tags_json = json.dumps(new_tags) if new_tags else None

    # discuss_with_teacher — boolean toggle. True flips the timestamp on
    # to `now`; False clears both the timestamp AND the note. Sending
    # the note alone (without `discuss_with_teacher`) just updates the
    # note while preserving on/off state.
    if "discuss_with_teacher" in patch:
        flag = bool(patch["discuss_with_teacher"])
        had = item.discuss_with_teacher_at is not None
        if flag and not had:
            _record("discuss_with_teacher", None, now.isoformat())
            item.discuss_with_teacher_at = now
        elif (not flag) and had:
            _record("discuss_with_teacher", item.discuss_with_teacher_at.isoformat(), None)
            item.discuss_with_teacher_at = None
            # Clearing the flag also clears any note that went with it —
            # otherwise a stale note resurfaces if the parent re-flags later.
            if item.discuss_with_teacher_note:
                _record("discuss_with_teacher_note", item.discuss_with_teacher_note, None)
                item.discuss_with_teacher_note = None

    if "discuss_with_teacher_note" in patch:
        raw = patch["discuss_with_teacher_note"]
        new_note = (raw or "").strip() or None
        if new_note != item.discuss_with_teacher_note:
            _record("discuss_with_teacher_note", item.discuss_with_teacher_note, new_note)
            item.discuss_with_teacher_note = new_note
            # Convenience: setting a note implicitly turns the flag on
            # (parent typed something — they meant to flag). Cleared note
            # alone does NOT turn the flag off (use discuss_with_teacher=false).
            if new_note and item.discuss_with_teacher_at is None:
                _record("discuss_with_teacher", None, now.isoformat())
                item.discuss_with_teacher_at = now

    for c in changes:
        session.add(c)
    await session.commit()
    await session.refresh(item)

    return {
        "id": item.id,
        "parent_status": item.parent_status,
        "priority": item.priority,
        "snooze_until": item.snooze_until,
        "status_notes": item.status_notes,
        "tags": parse_tags(item.tags_json),
        "discuss_with_teacher_at": (
            item.discuss_with_teacher_at.isoformat()
            if item.discuss_with_teacher_at else None
        ),
        "discuss_with_teacher_note": item.discuss_with_teacher_note,
    }


async def get_history(
    session: AsyncSession, item_id: int, limit: int = 200
) -> list[dict[str, Any]]:
    rows = (
        await session.execute(
            select(AssignmentStatusHistory)
            .where(AssignmentStatusHistory.item_id == item_id)
            .order_by(AssignmentStatusHistory.created_at.desc())
            .limit(limit)
        )
    ).scalars().all()
    return [
        {
            "id": r.id,
            "field": r.field,
            "old_value": r.old_value,
            "new_value": r.new_value,
            "source": r.source,
            "actor": r.actor,
            "note": r.note,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows
    ]
