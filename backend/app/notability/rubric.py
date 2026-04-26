"""Rubric: per-event-kind notability score + delivery tier + dedup_key.

Keep this file pure (no DB, no IO) so it can be unit-tested and retuned easily.
See BUILDSPEC §5.2.

Three delivery tiers introduced in Phase 14 govern *when* a notification fires:

  now    — fires immediately across enabled channels (telegram, email, inapp)
           subject to threshold + rate-limit gates. Reserved for the things a
           parent genuinely wants to hear about right now.

  today  — inapp only at fire time; rolled into the morning digest for
           email + telegram. Useful for "needs-attention but not urgent".

  weekly — inapp only, deferred to the weekly digest. The default for
           routine, low-signal events that would otherwise spam.

Every kind picks one tier explicitly here so there are no surprises. The
dispatcher reads `kind.tier` and chooses channels accordingly.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal


Tier = Literal["now", "today", "weekly"]


@dataclass(frozen=True)
class EventKind:
    name: str
    notability: float
    description: str
    tier: Tier = "today"  # explicit default — never silently routes to "now"

    def dedup_key(self, **parts: Any) -> str:
        bits = [self.name] + [f"{k}={v}" for k, v in parts.items() if v is not None]
        return ":".join(bits)


# "now" tier — these warrant immediate cross-channel delivery.
OVERDUE_7D = EventKind(
    "overdue_7d", 0.9, "Item crossed 7-days-overdue line", "now",
)
GRADE_POSTED_OUTLIER = EventKind(
    "grade_posted_outlier", 0.7, "Grade >1σ off trend", "now",
)
COMMENT_LONG = EventKind(
    "comment_long", 0.8, "Teacher comment ≥30 words", "now",
)
REPORT_CARD_POSTED = EventKind(
    "report_card_posted", 0.9, "New report card appears", "now",
)
SCRAPER_DRIFT = EventKind(
    "scraper_drift", 0.8, "Scraper saw fewer-than-expected rows", "now",
)
SYNC_FAILED = EventKind(
    "sync_failed", 1.0, "Sync errored out entirely", "now",
)
BACKLOG_ACCELERATING = EventKind(
    "backlog_accelerating", 0.7, "Overdue count up >50% in 48h", "now",
)
SUBJECT_CONCENTRATION = EventKind(
    "subject_concentration", 0.7,
    "One subject >40% of a child's overdue (≥4 items)", "now",
)
SYLLABUS_CHANGED = EventKind(
    "syllabus_changed", 0.8, "School updated the syllabus", "now",
)

# "today" tier — useful in the morning digest but doesn't need a buzz now.
NEW_ASSIGNMENT = EventKind(
    "new_assignment", 0.1, "Routine assignment posted", "today",
)
OVERDUE_3D = EventKind(
    "overdue_3d", 0.6, "Item crossed 3-days-overdue line", "today",
)
COMMENT_SHORT = EventKind(
    "comment_short", 0.5, "Teacher comment <30 words", "today",
)
SCHOOL_MESSAGE = EventKind(
    "school_message", 0.6, "New school-wide message", "today",
)
GRADE_POSTED_ROUTINE = EventKind(
    "grade_posted_routine", 0.2, "Grade within 1σ", "today",
)
FIRST_GRADE_OF_CYCLE = EventKind(
    "first_grade_of_cycle", 0.5, "First grade after new LC starts", "today",
)

# "weekly" tier — low signal, only the weekly digest.
ASSIGNMENT_SUBMITTED = EventKind(
    "assignment_submitted", 0.1, "Kid submitted something", "weekly",
)

# Digest events fire on schedule — they ARE the digest, so always "now".
DIGEST_4PM = EventKind("digest_4pm", 1.0, "Scheduled daily digest", "now")
DIGEST_WEEKLY = EventKind("digest_weekly", 1.0, "Scheduled weekly digest", "now")


ALL_KINDS: dict[str, EventKind] = {
    e.name: e
    for e in (
        NEW_ASSIGNMENT,
        ASSIGNMENT_SUBMITTED,
        GRADE_POSTED_ROUTINE,
        GRADE_POSTED_OUTLIER,
        COMMENT_SHORT,
        COMMENT_LONG,
        SCHOOL_MESSAGE,
        OVERDUE_3D,
        OVERDUE_7D,
        BACKLOG_ACCELERATING,
        SUBJECT_CONCENTRATION,
        FIRST_GRADE_OF_CYCLE,
        REPORT_CARD_POSTED,
        SCRAPER_DRIFT,
        SYNC_FAILED,
        DIGEST_4PM,
        DIGEST_WEEKLY,
        SYLLABUS_CHANGED,
    )
}


def tier_for(kind_name: str) -> Tier:
    """Default tier for a kind name. Defaults to 'today' if unknown."""
    k = ALL_KINDS.get(kind_name)
    return k.tier if k else "today"
