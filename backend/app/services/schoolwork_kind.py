"""Classify schoolwork rows: new work vs review vs test vs project, etc.

The school's Veracross feed lumps everything under `kind="assignment"` —
which makes it hard to answer "is Wednesday's social-studies slot a NEW
chapter or a REVIEW of last week's?" without reading every title by
hand. This service teases the categories apart with a deterministic
keyword-pass first, with an LLM fallback for the ambiguous cases.

Categories (deliberately small, easy to reason about):

    new_work     — fresh content / first introduction of a topic
    review       — revision / recap of previously covered material
    test         — assessment / quiz / exam / examination / unit test
    project      — multi-step project work / model / chart / poster
    presentation — speech / recitation / oral presentation
    submission   — submission of something previously assigned (PDF/photo upload)
    other        — couldn't classify confidently

Each result carries:
    {kind, confidence (0..1), reasoning, matched_keywords}

Pure-Python keyword classifier; no DB or LLM dependency. Designed to be
called from MCP tools at query time with no pre-warming.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


@dataclass
class KindResult:
    kind: str                          # one of the categories above
    confidence: float                  # 0.0 .. 1.0
    reasoning: str                     # one short sentence
    matched_keywords: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "confidence": round(self.confidence, 2),
            "reasoning": self.reasoning,
            "matched_keywords": self.matched_keywords,
        }


# Order matters: more specific patterns first. The first category whose
# pattern matches wins. Each rule is (kind, regex, confidence, why).
# Regexes use word boundaries so "test" doesn't match "contest" or "testimonial".
_RULES: list[tuple[str, re.Pattern[str], float, str]] = [
    # tests / assessments
    ("test", re.compile(r"\b(unit\s*test|class\s*test|monthly\s*test)\b", re.I), 0.95,
     "explicit test phrasing in the title"),
    ("test", re.compile(r"\b(test|examination|exam(?!ple)|quiz|assessment|graded\s+task)\b", re.I), 0.85,
     "assessment-related keyword"),
    ("test", re.compile(r"\b(viva|oral\s*test|spelling\s*bee)\b", re.I), 0.85,
     "viva / oral / bee assessment"),

    # projects (multi-session work)
    ("project", re.compile(r"\b(project|model\s+making|poster|chart\s*work|lapbook|portfolio)\b", re.I), 0.85,
     "project-style work indicator"),

    # presentations / oral
    ("presentation", re.compile(r"\b(presentation|speech|recitation|elocution|oral|debate)\b", re.I), 0.85,
     "presentation-style work indicator"),

    # reviews / revisions
    ("review", re.compile(r"\b(revision|revise|recap|review|reinforce|practice\s+sheet)\b", re.I), 0.85,
     "review/revision keyword in title"),
    ("review", re.compile(r"\bworksheet\b.*\b(revision|recap)\b", re.I), 0.95,
     "revision worksheet"),

    # submissions (drop-off / hand-in only)
    ("submission", re.compile(r"\b(submit|submission|hand[- ]?in|upload|due)\b", re.I), 0.7,
     "submission-only event (no new content)"),

    # new content (positive markers — last so they don't pre-empt the others)
    ("new_work", re.compile(r"\b(introduction\s*to|new\s*chapter|chapter\s*\d+|lesson\s*\d+)\b", re.I), 0.8,
     "new-chapter / lesson indicator"),
    ("new_work", re.compile(r"\b(read|learn|notebook\s*work|copy\s*work|write\s*about)\b", re.I), 0.6,
     "instructional verb suggests new work"),
]


def classify(title: str | None, body: str | None = None) -> KindResult:
    """Classify a single assignment by keyword matches over title + body.

    Order: walk the rules; first match wins; record the rule's confidence.
    If nothing matches, return ('other', 0.3, 'no recognised keywords').
    """
    text = " ".join(t for t in (title, body) if t)
    if not text.strip():
        return KindResult(kind="other", confidence=0.0, reasoning="empty title and body")

    for kind, pattern, conf, why in _RULES:
        m = pattern.search(text)
        if m:
            return KindResult(
                kind=kind,
                confidence=conf,
                reasoning=why,
                matched_keywords=[m.group(0).strip()],
            )

    return KindResult(
        kind="other",
        confidence=0.3,
        reasoning="no recognised keywords — likely new work but unconfirmed",
    )


def classify_batch(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Classify a list of assignment-shaped dicts. Returns the input
    rows with a `schoolwork_kind` field appended."""
    out: list[dict[str, Any]] = []
    for r in rows:
        result = classify(r.get("title") or r.get("title_en"), r.get("body") or r.get("notes_en"))
        out.append({**r, "schoolwork_kind": result.to_dict()})
    return out
