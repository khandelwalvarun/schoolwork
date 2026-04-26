"""Subject-name → language code classifier.

Vasant Valley's subject names are class-prefixed strings like
"6B Hindi", "4C English", "6B Sanskrit". We can derive the language
track from a substring match — no LLM call, no DB table, just a
lookup. Returning None means "not a language track" (math, science,
social science, etc.) — those still get sparklines, just without a
language chip.

Used by:
  - services/topic_state — stamps language_code on each TopicState row
  - services/grade_trends (frontend) — chips a sparkline with the lang
"""
from __future__ import annotations


# Order matters — Sanskrit can be a substring of nothing else but we
# check it first to be safe; Hindi before English so a multi-language
# composite subject (rare) lands on the more-specific code.
_LANGUAGE_HINTS: tuple[tuple[str, str], ...] = (
    ("sanskrit", "sa"),
    ("hindi", "hi"),
    ("english", "en"),
)


def language_code_for(subject: str | None) -> str | None:
    """Map a subject string to one of {en, hi, sa, None}.

    Examples:
        '6B Hindi'      → 'hi'
        '4C English'    → 'en'
        '6B Sanskrit'   → 'sa'
        '6B Mathematics'→ None  (not a language track)
        None / ''       → None
    """
    if not subject:
        return None
    s = subject.lower()
    for needle, code in _LANGUAGE_HINTS:
        if needle in s:
            return code
    return None


# Display labels for the UI — short to fit in chips.
LANGUAGE_LABEL: dict[str, str] = {
    "en": "English",
    "hi": "हिन्दी",
    "sa": "संस्कृत",
}
