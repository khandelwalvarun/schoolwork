"""Mindspark DOM parsers — pure HTML, no XHR / endpoint sniffing.

Per user direction: "do the entire job via Playwright driven browser
instead of hitting endpoints directly."

After Playwright drives the SPA (login + click "Topics" / "Leaderboard"
menus), we read the rendered DOM and extract what's there. No knowledge
of internal API shapes; if Mindspark redesigns the page we update the
selectors.

Three current parsers, matching what the menu-click recon walk
captures:

  parse_topics_page(html)
    `mat-card[id^="activeTopicCard"]` and `mat-card[id^="otherTopicCard"]`.
    Active = currently working on; Other = mastered/revise.

  parse_leaderboard_page(html)
    Section-level Sparkie ranking; finds the kid's own row, its rank,
    sparkies, and any badge title (e.g. "Fraction Whiz").

  parse_home_summary(html)
    Profile name + total Sparkies + alert count from the persistent
    top-bar.
"""
from __future__ import annotations

import logging
import re
from typing import Any

from bs4 import BeautifulSoup


log = logging.getLogger(__name__)


def _clean(s: str | None) -> str:
    if not s:
        return ""
    return re.sub(r"\s+", " ", s).strip()


# ─── topics page ────────────────────────────────────────────────────────────

def parse_topics_page(html: str) -> list[dict[str, Any]]:
    """Per-topic rows from /Student/student/topics. Returns:
      [
        {
          subject, topic_name, accuracy_pct, units_total,
          mastery_level (active|revise|mastered), card_id,
        }, ...
      ]

    Subject inference: Mindspark's /topics view is per-subject —
    the kid is on a single subject when they land here (Math
    primary). We look for known subject hints in the page; if
    none, the caller fills in.
    """
    if not html:
        return []
    soup = BeautifulSoup(html, "lxml")

    subject = None
    for sel in ("h1", "h2", ".subjectName", ".subject-name"):
        for el in soup.select(sel):
            t = _clean(el.get_text(" ", strip=True))
            if t.lower() in ("mathematics", "maths", "math", "english", "science"):
                subject = t.title()
                break
        if subject:
            break

    out: list[dict[str, Any]] = []

    def _parse_card(card, mastery_level: str) -> dict[str, Any] | None:
        title_el = card.select_one(".title")
        if title_el is None:
            return None
        topic_name = _clean(title_el.get_text(" ", strip=True))
        if not topic_name:
            return None
        units_total = None
        desc_el = card.select_one(".description")
        if desc_el is not None:
            desc = _clean(desc_el.get_text(" ", strip=True))
            m = re.search(r"(\d+)\s*units?", desc, re.I)
            if m:
                units_total = int(m.group(1))
        accuracy_pct = None
        prog_el = card.select_one(".progress")
        if prog_el is not None:
            t = _clean(prog_el.get_text(" ", strip=True))
            m = re.search(r"(\d+(?:\.\d+)?)\s*%", t)
            if m:
                accuracy_pct = float(m.group(1))
        return {
            "subject": subject,
            "topic_name": topic_name,
            "accuracy_pct": accuracy_pct,
            "units_total": units_total,
            "mastery_level": mastery_level,
            "card_id": card.get("id"),
        }

    for card in soup.select('mat-card[id^="activeTopicCard"]'):
        rec = _parse_card(card, "active")
        if rec:
            out.append(rec)
    for card in soup.select('mat-card[id^="otherTopicCard"]'):
        cls = card.get("class") or []
        level = "mastered" if "disabled" in cls else "revise"
        rec = _parse_card(card, level)
        if rec:
            out.append(rec)

    return out


# ─── leaderboard page ───────────────────────────────────────────────────────

def parse_leaderboard_page(
    html: str, child_name: str | None = None,
) -> dict[str, Any]:
    """Section-level ranking. Returns:
      {
        rank, sparkies, title,        # the kid's own row
        section_size,
        top_3: [{rank, name, sparkies, title}, ...],
        section_avg_sparkies,
      }
    """
    empty = {
        "rank": None, "sparkies": None, "title": None,
        "section_size": 0, "top_3": [], "section_avg_sparkies": None,
    }
    if not html:
        return empty
    soup = BeautifulSoup(html, "lxml")
    text = re.sub(r"\s+", " ", soup.get_text(" ")).strip()
    # Slice past chrome.
    m = re.search(r"Sparkie Leaderboard\s+\w+\s+\d{4}\s+", text)
    sliced = text[m.end():] if m else text

    # Each row: "<rank> <words…> <number> Sparkies earned".
    # Splitting name from title is heuristic — Mindspark title strings
    # are short, multi-word, and contain a known stem ("Whiz", "Champ",
    # "Star", "Master", "Brain", "Pro"). Anything before that stem is
    # the name; the stem-bearing tail (and the word before it) is the
    # title. If no known stem, the entire word run is the name.
    KNOWN_TITLE_STEMS = (
        "whiz", "champ", "star", "master", "brain", "pro",
        "wizard", "explorer", "ninja", "champion",
    )
    pattern = re.compile(
        r"(\d+)\s+(.+?)\s+(\d+)\s+Sparkies\s+earned",
        re.UNICODE,
    )
    rows: list[dict[str, Any]] = []
    for m in pattern.finditer(sliced):
        rank = int(m.group(1))
        words_run = _clean(m.group(2))
        sparkies = int(m.group(3))
        words = words_run.split()
        title_idx = None
        for i, w in enumerate(words):
            if w.lower() in KNOWN_TITLE_STEMS:
                title_idx = i
                break
        if title_idx is not None and title_idx >= 1:
            # Title is from the word before the stem to the end.
            split_at = max(2, title_idx - 1)  # keep at least 2-word name
            name = " ".join(words[:split_at])
            title = " ".join(words[split_at:])
        else:
            name = words_run
            title = None
        rows.append({
            "rank": rank,
            "name": name.strip(),
            "title": title.strip() if title else None,
            "sparkies": sparkies,
        })

    self_row = None
    if child_name and rows:
        first = child_name.split()[0].lower()
        for r in rows:
            if first in r["name"].lower():
                self_row = r
                break

    avg = sum(r["sparkies"] for r in rows) / len(rows) if rows else None

    return {
        "rank": self_row["rank"] if self_row else None,
        "sparkies": self_row["sparkies"] if self_row else None,
        "title": self_row["title"] if self_row else None,
        "section_size": len(rows),
        "top_3": rows[:3],
        "section_avg_sparkies": avg,
    }


# ─── home / top-bar summary ─────────────────────────────────────────────────

def parse_home_summary(html: str) -> dict[str, Any]:
    """Pull profile name + sparkie count + alert count from the
    persistent top-bar that's present on every authenticated page."""
    empty = {"name": None, "sparkies": None, "alerts": None}
    if not html:
        return empty
    soup = BeautifulSoup(html, "lxml")
    text = re.sub(r"\s+", " ", soup.get_text(" ")).strip()
    name = None
    m = re.search(
        r"Mindspark \| Student\s+([A-Z][A-Za-z'\-]+(?:\s+[A-Z][A-Za-z'\-]+){0,3})",
        text,
    )
    if m:
        name = m.group(1).strip()
    sparkies = None
    if name:
        m = re.search(rf"{re.escape(name)}\s+(\d+)\s+Alert", text)
        if m:
            sparkies = int(m.group(1))
    alerts = None
    m = re.search(r"Alert\s+(\d+)\s+feedback", text)
    if m:
        alerts = int(m.group(1))
    return {"name": name, "sparkies": sparkies, "alerts": alerts}


# ─── back-compat shims ──────────────────────────────────────────────────────

def parse_sessions(html: str) -> list[dict[str, Any]]:
    """Deprecated. Mindspark's session-history view requires a
    different click flow; we now derive activity signals from
    parse_topics_page() (active vs revise) and the leaderboard
    sparkie count over time."""
    return []


def parse_topic_progress(html: str) -> list[dict[str, Any]]:
    """Compatibility alias for sync.run_metrics_for. Returns the
    new-shape rows so the upsert path works without changes."""
    return parse_topics_page(html)
