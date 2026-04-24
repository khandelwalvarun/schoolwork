"""Rubric: per-event-kind notability score + dedup_key template.

Keep this file pure (no DB, no IO) so it can be unit-tested and retuned easily.
See BUILDSPEC §5.2.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class EventKind:
    name: str
    notability: float
    description: str

    def dedup_key(self, **parts: Any) -> str:
        bits = [self.name] + [f"{k}={v}" for k, v in parts.items() if v is not None]
        return ":".join(bits)


NEW_ASSIGNMENT = EventKind("new_assignment", 0.1, "Routine assignment posted")
ASSIGNMENT_SUBMITTED = EventKind("assignment_submitted", 0.1, "Kid submitted something")
GRADE_POSTED_ROUTINE = EventKind("grade_posted_routine", 0.2, "Grade within 1σ")
GRADE_POSTED_OUTLIER = EventKind("grade_posted_outlier", 0.7, "Grade >1σ off trend")
COMMENT_SHORT = EventKind("comment_short", 0.5, "Teacher comment <30 words")
COMMENT_LONG = EventKind("comment_long", 0.8, "Teacher comment ≥30 words")
SCHOOL_MESSAGE = EventKind("school_message", 0.6, "New school-wide message")
OVERDUE_3D = EventKind("overdue_3d", 0.6, "Item crossed 3-days-overdue line")
OVERDUE_7D = EventKind("overdue_7d", 0.9, "Item crossed 7-days-overdue line")
BACKLOG_ACCELERATING = EventKind("backlog_accelerating", 0.7, "Overdue count up >50% in 48h")
SUBJECT_CONCENTRATION = EventKind(
    "subject_concentration", 0.7, "One subject >40% of a child's overdue (≥4 items)"
)
FIRST_GRADE_OF_CYCLE = EventKind("first_grade_of_cycle", 0.5, "First grade after new LC starts")
REPORT_CARD_POSTED = EventKind("report_card_posted", 0.9, "New report card appears")
SCRAPER_DRIFT = EventKind("scraper_drift", 0.8, "Scraper saw fewer-than-expected rows")
SYNC_FAILED = EventKind("sync_failed", 1.0, "Sync errored out entirely")
DIGEST_4PM = EventKind("digest_4pm", 1.0, "Scheduled daily digest")
DIGEST_WEEKLY = EventKind("digest_weekly", 1.0, "Scheduled weekly digest")
SYLLABUS_CHANGED = EventKind("syllabus_changed", 0.8, "School updated the syllabus")

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
