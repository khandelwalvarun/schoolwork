"""Mindspark HTML/JSON parsers.

These are FIRST-PASS BEST GUESSES based on the recon agent's spec,
not on real captures. After running `run_recon_for(child_id)` once
the user can hand back the dumped JSON files in
data/mindspark_recon/<child>/<ts>/, and we'll refine these to match
the actual response shapes.

Until then both `parse_sessions` and `parse_topic_progress` may
return [] on a real page — that's OK; the recon mode is the right
first step. The downstream `sync.py:run_metrics_for` no-ops cleanly
on empty parses.
"""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from typing import Any

from bs4 import BeautifulSoup


log = logging.getLogger(__name__)


# ─── sessions ───────────────────────────────────────────────────────────────

def parse_sessions(html: str) -> list[dict[str, Any]]:
    """Extract recent session rows from the dashboard.

    Best-guess: Mindspark's SPA likely renders sessions as a list of
    cards with class `session-card` / `recent-session` / similar. We
    look for any structured data attribute containing session ids,
    plus inline `<script>` blobs that carry initial state.

    Returns a list of dicts with keys (any subset; sync.py is robust
    to missing keys):
      external_id, subject, topic_name, started_at, ended_at,
      duration_sec, questions_total, questions_correct, accuracy_pct
    """
    if not html:
        return []
    soup = BeautifulSoup(html, "lxml")
    out: list[dict[str, Any]] = []

    # 1) data-session-id-bearing nodes
    for el in soup.select("[data-session-id]"):
        sid = el.get("data-session-id")
        if not sid:
            continue
        rec = {"external_id": sid}
        # Try to glean accuracy / questions from common labels.
        text = el.get_text(" ", strip=True).lower()
        m = re.search(r"(\d+)\s*/\s*(\d+)\s*correct", text)
        if m:
            rec["questions_correct"] = int(m.group(1))
            rec["questions_total"] = int(m.group(2))
            if rec["questions_total"]:
                rec["accuracy_pct"] = (
                    100.0 * rec["questions_correct"] / rec["questions_total"]
                )
        m = re.search(r"(\d+(?:\.\d+)?)\s*%", text)
        if m and "accuracy_pct" not in rec:
            rec["accuracy_pct"] = float(m.group(1))
        m = re.search(r"(\d+)\s*min", text)
        if m:
            rec["duration_sec"] = int(m.group(1)) * 60
        for label in ("Mathematics", "English", "Science"):
            if label.lower() in text:
                rec["subject"] = label
                break
        out.append(rec)

    # 2) inline script data — Angular `<script id="ngState">` etc.
    for script in soup.find_all("script"):
        s = script.string or ""
        if not s:
            continue
        # Heuristic: find a JSON-like object containing 'sessionId'.
        if "sessionId" not in s:
            continue
        # Try to extract individual {…} chunks that look like sessions.
        for match in re.finditer(r"\{[^{}]*sessionId[^{}]*\}", s):
            blob = match.group(0)
            try:
                obj = json.loads(blob)
            except Exception:
                continue
            if isinstance(obj, dict) and obj.get("sessionId"):
                out.append({
                    "external_id": str(obj["sessionId"]),
                    "subject": obj.get("subject"),
                    "topic_name": obj.get("topic") or obj.get("topicName"),
                    "questions_total": obj.get("questionsTotal") or obj.get("totalQuestions"),
                    "questions_correct": obj.get("questionsCorrect") or obj.get("correct"),
                    "accuracy_pct": obj.get("accuracy") or obj.get("score"),
                    "duration_sec": obj.get("durationSec"),
                })

    # Dedupe by external_id, last write wins.
    by_id: dict[str, dict[str, Any]] = {}
    for rec in out:
        eid = str(rec.get("external_id") or "").strip()
        if not eid:
            continue
        by_id[eid] = rec
    return list(by_id.values())


# ─── topic progress ─────────────────────────────────────────────────────────

def parse_topic_progress(html: str) -> list[dict[str, Any]]:
    """Extract per-topic progress rows from the topic-map page.

    Best-guess: each topic is a card with a subject label, topic name,
    accuracy / mastery indicator (often a 0-100 numeric or a band like
    "beginner / proficient / mastered"), and an attempts count.
    """
    if not html:
        return []
    soup = BeautifulSoup(html, "lxml")
    out: list[dict[str, Any]] = []

    # 1) data-topic-id-bearing nodes (most reliable when present)
    for el in soup.select("[data-topic-id]"):
        tid = el.get("data-topic-id")
        if not tid:
            continue
        text = el.get_text(" ", strip=True)
        rec: dict[str, Any] = {
            "topic_id": tid,
            "topic_name": (
                el.get("data-topic-name")
                or (el.find(class_=re.compile("topic-name|topic-title", re.I)) or {}).get("text", "")
                if el.find(class_=re.compile("topic-name|topic-title", re.I)) else ""
            ),
            "subject": (
                el.get("data-subject")
                or _find_subject_label(el)
                or "Mathematics"  # most common; remove this default after recon
            ),
        }
        if not rec["topic_name"]:
            # Try a heading inside the card.
            h = el.find(["h2", "h3", "h4"])
            rec["topic_name"] = h.get_text(strip=True) if h else ""
        m = re.search(r"(\d+(?:\.\d+)?)\s*%", text)
        if m:
            rec["accuracy_pct"] = float(m.group(1))
        m = re.search(r"(\d+)\s*(?:question|attempt)", text, re.I)
        if m:
            rec["questions_attempted"] = int(m.group(1))
        for level in ("Beginner", "Proficient", "Mastered", "Advanced", "Familiar"):
            if level.lower() in text.lower():
                rec["mastery_level"] = level.lower()
                break
        if rec["topic_name"]:
            out.append(rec)

    # 2) script-tag JSON state
    for script in soup.find_all("script"):
        s = script.string or ""
        if "topicId" not in s and "topic_id" not in s:
            continue
        for match in re.finditer(r"\{[^{}]*topic[Ii]d[^{}]*\}", s):
            blob = match.group(0)
            try:
                obj = json.loads(blob)
            except Exception:
                continue
            if isinstance(obj, dict):
                rec = {
                    "topic_id": str(obj.get("topicId") or obj.get("topic_id") or ""),
                    "topic_name": obj.get("topicName") or obj.get("topic_name") or obj.get("name"),
                    "subject": obj.get("subject") or obj.get("subjectName"),
                    "accuracy_pct": obj.get("accuracy") or obj.get("accuracyPct"),
                    "questions_attempted": obj.get("attempts") or obj.get("questionsAttempted"),
                    "mastery_level": obj.get("masteryLevel") or obj.get("mastery"),
                }
                if rec["topic_name"]:
                    out.append(rec)

    # Dedupe by (subject, topic_name).
    by_key: dict[tuple[str, str], dict[str, Any]] = {}
    for rec in out:
        k = (str(rec.get("subject") or "Mathematics"), str(rec.get("topic_name") or ""))
        if k[1]:
            by_key[k] = {**rec, "subject": k[0]}
    return list(by_key.values())


def _find_subject_label(el) -> str | None:
    parent = el
    for _ in range(3):
        if parent is None:
            break
        # Look for known subject names in nearby text or attributes.
        text = " ".join(filter(None, [
            parent.get("data-subject") if hasattr(parent, "get") else None,
            parent.get_text(" ", strip=True) if hasattr(parent, "get_text") else None,
        ]))
        for label in ("Mathematics", "English", "Science"):
            if label.lower() in (text or "").lower():
                return label
        parent = getattr(parent, "parent", None)
    return None
