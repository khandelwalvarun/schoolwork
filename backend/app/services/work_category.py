"""Three-bucket classifier for Veracross assignment rows.

The school's feed labels every row with `normalized.type` (Homework /
Classwork / Review plus skill labels). We collapse that to three
actionable buckets:

  classwork  — done in class, parent doesn't track or take action.
               Filtered out of overdue / due_today / upcoming.
  homework   — to-be-done-at-home work with a due date. Full status
               tracking + practice/help/check workflow.
  review     — assessment / test / quiz / revision. Drives the prep
               workflow + gets visual emphasis on every surface.

100% deterministic — pure dict lookup against Veracross's own `type`
field. No title regex, no LLM. When the type is missing or unmapped,
the row is left UNCLASSIFIED (None) so unknown values surface in
logs and UI rather than being silently guessed at. Extending the
mapping is a one-line change here when the school introduces a new
type.
"""
from __future__ import annotations

import logging
from typing import Any


log = logging.getLogger(__name__)


CLASSWORK = "classwork"
HOMEWORK = "homework"
REVIEW = "review"
ALLOWED = {CLASSWORK, HOMEWORK, REVIEW}


# Veracross's `type` field → our three buckets. Lower-cased keys; the
# input is normalised before lookup. Mapping decisions:
#   - "Classwork" → classwork (the kid did it in class; we don't action)
#   - "Homework" → homework (take-home work)
#   - "Review" + assessment-shaped skill types → review (graded check)
#   - Creative-skill types → homework (the kid does it at home, the
#     teacher grades it under that skill label)
#
# When the school introduces a new type, this dict is the one place
# to extend. Unknown types stay NULL — visible in the unknown-type
# log warning and on the UI as "uncategorized" — so we don't silently
# misclassify.
_TYPE_TO_CATEGORY: dict[str, str] = {
    "homework": HOMEWORK,
    "classwork": CLASSWORK,
    "review": REVIEW,
    # Skill-graded assessment categories
    "memory and recall": REVIEW,
    "logical reasoning": REVIEW,
    "application": REVIEW,
    "computation": REVIEW,
    "comprehension": REVIEW,
    "techniques": REVIEW,
    "grammar and vocabulary": REVIEW,
    "research skills": REVIEW,
    # Skill-graded creative-work categories (still done as homework)
    "writing skills": HOMEWORK,
    "speaking skills": HOMEWORK,
    "reading skills": HOMEWORK,
    # Explicit test-shaped types (rare — usually folded into Review)
    "test": REVIEW,
    "quiz": REVIEW,
    "assessment": REVIEW,
    "exam": REVIEW,
    "examination": REVIEW,
    "viva": REVIEW,
    "spelling bee": REVIEW,
}


# Cache of unknown-type names we've already warned about so the log
# stays small even on a big sync run. Dropped when the process restarts.
_warned_unknown: set[str] = set()


def classify(
    *,
    normalized_type: str | None = None,
    title: str | None = None,  # accepted but unused — kept in sig for caller compat
    body: str | None = None,   # accepted but unused
) -> str | None:
    """Map a Veracross row to one of {classwork, homework, review}.

    Pure-dict lookup against Veracross's own `type` field. Returns
    None when:
      - `normalized_type` is missing (the parser couldn't read it)
      - `normalized_type` is set but not in our mapping (new label
        from the school we haven't seen)

    Unknown types are warned-once to the log; extend the mapping in
    this file to add coverage.
    """
    if not normalized_type:
        return None
    key = normalized_type.strip().lower()
    cat = _TYPE_TO_CATEGORY.get(key)
    if cat is None and key and key not in _warned_unknown:
        _warned_unknown.add(key)
        log.warning(
            "work_category: unknown Veracross type %r — leaving row unclassified. "
            "Extend services/work_category._TYPE_TO_CATEGORY to map it.",
            normalized_type,
        )
    return cat


def classify_from_normalized(
    normalized_json_str: str | None,
    title: str | None = None,
    body: str | None = None,
) -> str | None:
    """Convenience wrapper: takes the raw normalized_json string from
    the DB, returns the category or None."""
    import json as _json
    raw_type: str | None = None
    if normalized_json_str:
        try:
            n = _json.loads(normalized_json_str)
            if isinstance(n, dict):
                t = n.get("type")
                if isinstance(t, str):
                    raw_type = t
        except Exception:
            pass
    return classify(normalized_type=raw_type, title=title, body=body)
