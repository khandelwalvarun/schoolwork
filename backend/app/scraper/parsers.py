"""Pure HTML → dict parsers for Veracross pages.

Each parser takes raw HTML, returns plain dicts. No DB, no IO.
"""

from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any
from urllib.parse import urljoin

from bs4 import BeautifulSoup, Tag

_MONTH_RE = re.compile(
    r"(?P<dow>\w+day),\s*(?P<mon>Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+(?P<day>\d{1,2})",
    re.I,
)
_MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}


def _parse_long_date(text: str, assume_year: int) -> date | None:
    """'Tuesday, Apr 07' or 'Apr 07' → date. Year inferred from `assume_year`
    with a simple wrap-back rule for Jan/Feb on late-year scrapes."""
    m = _MONTH_RE.search(text) if text else None
    if m:
        mon = _MONTHS.get(m.group("mon").lower()[:3])
        day = int(m.group("day"))
        if mon:
            return date(assume_year, mon, day)
    short = re.search(r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+(\d{1,2})", text or "", re.I)
    if short:
        mon = _MONTHS.get(short.group(1).lower()[:3])
        day = int(short.group(2))
        if mon:
            return date(assume_year, mon, day)
    return None


# ─── planner (portals-embed planner page) ─────────────────────────────────────

def parse_planner(html: str, vc_id: str, assume_year: int | None = None) -> dict[str, Any]:
    """Parse the planner page for one child.

    Returns:
        {
            "classes": [{row_id, subject, teacher, website_url, assignments_url}],
            "assignments": [
                {external_id, type, title, status, subject (best-effort),
                 due_date (best-effort), teacher (best-effort), row_id}
            ],
            "raw_title": str,
        }
    """
    soup = BeautifulSoup(html, "lxml")
    year = assume_year or datetime.now().year

    classes: list[dict[str, Any]] = []
    row_id_to_class: dict[str, dict[str, Any]] = {}

    for row in soup.select(".timeline-row[data-row-id]"):
        row_id = row.get("data-row-id") or ""
        first_cell = row.find("div", class_="timeline-cell")
        if not isinstance(first_cell, Tag):
            continue
        title_el = first_cell.find(class_="title")
        teacher_el = first_cell.find(class_="subtitle")
        if title_el is None:
            continue
        subject = title_el.get_text(" ", strip=True)
        teacher = teacher_el.get_text(" ", strip=True) if teacher_el else None
        website = None
        assignments_url = None
        for a in first_cell.find_all("a"):
            href = a.get("href") or ""
            text = a.get_text(" ", strip=True).lower()
            if "website" in text or "class website" in text:
                website = href
            elif "assignments" in text:
                assignments_url = href
        # Extract class_id from any URL that contains /classes/{cid}.
        class_id: str | None = None
        for candidate in (assignments_url, website):
            if not candidate:
                continue
            m = re.search(r"/classes/(\d+)", candidate)
            if m:
                class_id = m.group(1)
                break
        cls = {
            "row_id": row_id,
            "class_id": class_id,
            "subject": subject,
            "teacher": teacher,
            "website_url": website,
            "assignments_url": assignments_url,
        }
        classes.append(cls)
        row_id_to_class[row_id] = cls

    # Map column index → date using the header row cells.
    column_dates: dict[int, date | None] = {}
    header_row = None
    for row in soup.select(".timeline-row.header"):
        # Header rows appear repeatedly (sticky headers). The first one with date strings works.
        cells = row.find_all("div", class_="timeline-cell", recursive=False)
        if cells and any(_parse_long_date(c.get_text(" ", strip=True), year) for c in cells):
            header_row = row
            break
    if header_row:
        cells = header_row.find_all("div", class_="timeline-cell", recursive=False)
        for idx, c in enumerate(cells):
            column_dates[idx] = _parse_long_date(c.get_text(" ", strip=True), year)

    # Pass 1: assignments found inside a class row (have subject/teacher/date).
    # Only iterate real class rows (those we captured above).
    by_id: dict[str, dict[str, Any]] = {}
    captured_row_ids = {c["row_id"] for c in classes}
    for row in soup.select(".timeline-row[data-row-id]"):
        row_id = row.get("data-row-id") or ""
        if row_id not in captured_row_ids:
            continue
        cls = row_id_to_class.get(row_id, {})
        cells = row.find_all("div", class_="timeline-cell", recursive=False)
        for idx, cell in enumerate(cells):
            for a in cell.select(".assignment[data-assignment-id]"):
                aid = a.get("data-assignment-id") or ""
                if not aid:
                    continue
                type_el = a.find(class_="assignment-type")
                desc_el = a.find(class_="assignment-description")
                badge_el = a.find(class_="badge")
                by_id[aid] = {
                    "external_id": aid,
                    "type": type_el.get_text(strip=True) if type_el else None,
                    "title": desc_el.get_text(strip=True) if desc_el else None,
                    "status_badge": (badge_el.get_text(strip=True) if badge_el else "").lower(),
                    "subject": cls.get("subject"),
                    "teacher": cls.get("teacher"),
                    "due_date": column_dates.get(idx).isoformat()
                    if column_dates.get(idx)
                    else None,
                    "row_id": row_id,
                }

    # Pass 2: any assignments that only appeared in the summary/due row — keep them
    # without subject; we'll fill from /detail/assignment/{id}.
    for a in soup.select(".assignment[data-assignment-id]"):
        aid = a.get("data-assignment-id") or ""
        if not aid or aid in by_id:
            continue
        type_el = a.find(class_="assignment-type")
        desc_el = a.find(class_="assignment-description")
        badge_el = a.find(class_="badge")
        by_id[aid] = {
            "external_id": aid,
            "type": type_el.get_text(strip=True) if type_el else None,
            "title": desc_el.get_text(strip=True) if desc_el else None,
            "status_badge": (badge_el.get_text(strip=True) if badge_el else "").lower(),
            "subject": None,
            "teacher": None,
            "due_date": None,
            "row_id": None,
        }

    assignments = list(by_id.values())

    return {
        "classes": classes,
        "assignments": assignments,
        "raw_title": (soup.title.string or "").strip() if soup.title else "",
    }


# ─── /detail/assignment/{id} (main portal) ────────────────────────────────────

def parse_assignment_detail(html: str) -> dict[str, Any]:
    """Parse `.vx-data-field` blocks on the assignment detail page.

    Returns dict with well-known keys if present, plus raw_fields dict for the rest.
    """
    soup = BeautifulSoup(html, "lxml")
    root = soup.find(class_="detail-assignment") or soup

    # Header
    course = root.select_one(".vx-record-header__course-description")
    teacher = root.select_one(".vx-record-header .vx-subtitle")
    record_type = root.select_one(".vx-record-header__type")

    # Body
    title = root.select_one(".vx-record-body .vx-record-title")
    type_text = root.select_one(".vx-record-body .vx-record-title-type")

    fields: dict[str, str] = {}
    for f in root.select(".vx-data-field"):
        label_el = f.find("small", class_="vx-subtitle")
        value_el = f.find(class_="vx-data-field__data") or f.find(
            class_="vx-data-field__notes"
        )
        if not label_el or not value_el:
            continue
        label = label_el.get_text(" ", strip=True)
        value = value_el.get_text(" ", strip=True)
        fields[label] = value

    return {
        "subject": course.get_text(" ", strip=True) if course else None,
        "teacher": teacher.get_text(" ", strip=True) if teacher else None,
        "record_type": record_type.get_text(" ", strip=True) if record_type else None,
        "title": title.get_text(" ", strip=True) if title else None,
        "type": type_text.get_text(" ", strip=True) if type_text else None,
        "date_assigned": fields.get("Date Assigned"),
        "due_date": fields.get("Due Date"),
        "max_score": fields.get("Max Score"),
        "weight": fields.get("Weight"),
        "notes": fields.get("Notes"),
        "raw_fields": fields,
    }


# ─── /messages (main portal) ──────────────────────────────────────────────────

def parse_messages_list(html: str, base_url: str) -> list[dict[str, Any]]:
    """List view of school messages. Each row gives from / subject / category / date /
    detail URL."""
    soup = BeautifulSoup(html, "lxml")
    out: list[dict[str, Any]] = []
    for item in soup.select(".vx-list__item.message"):
        link = item.find("a", class_="message-link") or item.find("a", href=True)
        href = link.get("href") if link else None
        # Extract external_id from /detail/email/{id}
        m = re.search(r"/detail/email/(\d+)", href or "")
        ext_id = m.group(1) if m else None
        if not ext_id:
            continue

        def _txt(cls: str) -> str | None:
            el = item.find(class_=cls)
            return el.get_text(" ", strip=True) if el else None

        out.append(
            {
                "external_id": ext_id,
                "from": _txt("message-from"),
                "from_label": _txt("message-from-label"),
                "subject": _txt("message-subject"),
                "category": _txt("message-category"),
                "date_sent": _txt("message-date-sent"),
                "detail_url": urljoin(base_url, href) if href else None,
            }
        )
    return out


# ─── /detail/email/{id} (main portal) ─────────────────────────────────────────

def parse_email_detail(html: str) -> dict[str, Any]:
    soup = BeautifulSoup(html, "lxml")
    # Veracross uses vx-record-* layout here too.
    root = soup.find(class_="detail-email") or soup
    title = root.select_one(".vx-record-title") or soup.find("h1")
    body_el = root.select_one(".vx-record-body") or root
    body_text = body_el.get_text("\n", strip=True) if body_el else ""
    fields: dict[str, str] = {}
    for f in root.select(".vx-data-field"):
        label_el = f.find("small", class_="vx-subtitle")
        value_el = f.find(class_="vx-data-field__data") or f.find(
            class_="vx-data-field__notes"
        )
        if label_el and value_el:
            fields[label_el.get_text(strip=True)] = value_el.get_text(" ", strip=True)
    return {
        "title": title.get_text(" ", strip=True) if title else None,
        "from": fields.get("From"),
        "sent": fields.get("Sent") or fields.get("Date"),
        "to": fields.get("To"),
        "body": body_text,
        "raw_fields": fields,
    }


# ─── documents.veracross.eu grade report ──────────────────────────────────────

_SCORE_FRAC_RE = re.compile(r"^\s*([0-9.]+)\s*/\s*([0-9.]+)\s*$")
_PCT_RE = re.compile(r"([0-9.]+)\s*%")


def parse_grade_report(html: str, class_id: str, grading_period: int) -> dict[str, Any]:
    """Parse a `documents.veracross.eu/.../grade_detail/{cid}?grading_period=N` HTML
    page. Returns:
        {
            "summary": [{type, earned, possible, average}],
            "grades": [{external_id (synthetic), due_date, assignment, score_text,
                        grade_pct, points_earned, points_possible, assignment_type}],
        }
    """
    soup = BeautifulSoup(html, "lxml")
    tables = soup.find_all("table", class_="data_table")
    summary: list[dict[str, Any]] = []
    grades: list[dict[str, Any]] = []

    # Summary table (first data_table) — no "grades" class.
    for t in tables:
        cls = t.get("class") or []
        if "grades" in cls:
            continue
        rows = t.find_all("tr")
        if not rows:
            continue
        headers = [h.get_text(" ", strip=True) for h in rows[0].find_all(["th", "td"])]
        for tr in rows[1:]:
            cells = [c.get_text(" ", strip=True) for c in tr.find_all(["td", "th"])]
            if not cells:
                continue
            row: dict[str, Any] = {}
            for i, h in enumerate(headers):
                if i < len(cells):
                    row[h.lower().replace(" ", "_").rstrip("*").rstrip("_")] = cells[i]
            summary.append(row)

    # Grades table — has both "data_table" and "grades" classes.
    for t in tables:
        cls = t.get("class") or []
        if "grades" not in cls:
            continue
        current_type: str | None = None
        header_cells: list[str] = []
        for tr in t.find_all("tr"):
            cells = tr.find_all(["td", "th"])
            if not cells:
                continue
            texts = [c.get_text(" ", strip=True) for c in cells]
            is_th_only = all(c.name == "th" for c in cells)
            # Multi-column <th> row → real header row
            if is_th_only and len(cells) > 1:
                header_cells = [x.lower().replace(" ", "_") for x in texts]
                continue
            # Single-cell row (th or td) or first-col-only → assignment-type group header.
            if len(cells) == 1 or (len(texts) >= 1 and texts[0] and all(t == "" for t in texts[1:])):
                current_type = texts[0]
                continue
            # Data row
            row = {}
            for i, h in enumerate(header_cells):
                if i < len(texts):
                    row[h] = texts[i]
            # Skip subtotal rows (first cell empty)
            if not row.get("assignment") and not row.get("due_date"):
                continue
            # Parse score text like "7.5 / 10"
            score_text = row.get("score", "")
            earned = possible = None
            m = _SCORE_FRAC_RE.match(score_text)
            if m:
                try:
                    earned = float(m.group(1))
                    possible = float(m.group(2))
                except ValueError:
                    pass
            grade_pct = None
            pm = _PCT_RE.search(row.get("grade", ""))
            if pm:
                try:
                    grade_pct = float(pm.group(1))
                except ValueError:
                    pass
            ext = f"{class_id}:p{grading_period}:{row.get('due_date','')}:{row.get('assignment','')[:40]}"
            grades.append(
                {
                    "external_id": ext,
                    "class_id": class_id,
                    "grading_period": grading_period,
                    "assignment_type": current_type,
                    "due_date": row.get("due_date"),
                    "assignment": row.get("assignment"),
                    "score_text": score_text,
                    "grade_pct": grade_pct,
                    "points_earned": earned,
                    "points_possible": possible,
                }
            )

    return {"summary": summary, "grades": grades}


# ─── status-badge translation ─────────────────────────────────────────────────

# Planner badge text → our canonical status enum (per BUILDSPEC §4).
_BADGE_MAP = {
    "due": "assigned",
    "overdue": "overdue",
    "submitted": "submitted",
    "graded": "graded",
}


def status_from_badge(badge_text: str | None, due_iso: str | None, today_iso: str) -> str:
    """Pick a canonical status for an assignment row."""
    if badge_text:
        for k, v in _BADGE_MAP.items():
            if k in badge_text:
                # "due" badge on a past date means overdue.
                if v == "assigned" and due_iso and due_iso < today_iso:
                    return "overdue"
                return v
    if due_iso and due_iso < today_iso:
        return "overdue"
    return "assigned"
