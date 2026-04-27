"""Syllabus structural validator.

Walks `data/syllabus/class_<N>_<year>.json` and reports format issues
the React UI can't catch on its own:

  - Cycle dates that overlap (LC1 ends 22 May, LC2 starts 20 May)
  - Cycle dates that have gaps (LC1 ends 22 May, LC2 starts 1 Jun)
  - ISO-date parse failures
  - Cycle order mismatched with start dates (LC2 listed before LC1)
  - Empty / missing topics_by_subject
  - Subjects with empty topic lists
  - Duplicate topic strings within a subject (after trim+lower)
  - Trailing / leading whitespace on topic strings
  - Suspicious mojibake markers in non-Latin titles
  - Mismatch between filename's class_level and the JSON's class_level field

Pure-Python; reads the syllabus JSON directly, no DB session needed.
Returned shape is JSON-safe so the MCP tool can return it as-is.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

from ..config import REPO_ROOT


SYLLABUS_DIR = REPO_ROOT / "data" / "syllabus"

# These two characters tend to show up in Devanagari that's been
# round-tripped through latin-1 by mistake. They're a strong signal of
# decoding bugs even though we can't autocorrect them blindly.
_MOJIBAKE_MARKERS = ("Ã", "â€", "â\x80", "Â\xa0", "à¤", "à¥")


@dataclass
class Issue:
    severity: str           # "error" | "warning" | "info"
    where: str              # path-like locator (e.g. "cycles[1].start")
    message: str

    def to_dict(self) -> dict[str, Any]:
        return {"severity": self.severity, "where": self.where, "message": self.message}


@dataclass
class ValidationReport:
    class_level: int
    file_path: str
    file_exists: bool
    issues: list[Issue] = field(default_factory=list)
    summary: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "class_level": self.class_level,
            "file_path": self.file_path,
            "file_exists": self.file_exists,
            "issues": [i.to_dict() for i in self.issues],
            "summary": self.summary,
            "ok": self.summary.get("error", 0) == 0,
        }


def _file_for(class_level: int) -> Path:
    matches = sorted(SYLLABUS_DIR.glob(f"class_{class_level}_*.json"))
    if matches:
        return matches[-1]  # newest year if multiple
    return SYLLABUS_DIR / f"class_{class_level}_2026-27.json"


def _load(path: Path) -> tuple[dict[str, Any] | None, str | None]:
    if not path.exists():
        return None, None
    try:
        return json.loads(path.read_text(encoding="utf-8")), None
    except json.JSONDecodeError as e:
        return None, f"invalid JSON: line {e.lineno} col {e.colno}: {e.msg}"
    except Exception as e:
        return None, f"failed to read: {e}"


def _parse_iso(s: Any) -> date | None:
    if not isinstance(s, str):
        return None
    try:
        return date.fromisoformat(s)
    except Exception:
        return None


def _has_mojibake(s: str) -> bool:
    return any(marker in s for marker in _MOJIBAKE_MARKERS)


def validate(class_level: int) -> ValidationReport:
    """Run all checks against the syllabus for a single class level."""
    path = _file_for(class_level)
    report = ValidationReport(
        class_level=class_level,
        file_path=str(path.relative_to(REPO_ROOT)) if str(path).startswith(str(REPO_ROOT)) else str(path),
        file_exists=path.exists(),
    )

    if not path.exists():
        report.issues.append(Issue(
            severity="error",
            where="file",
            message=f"syllabus file does not exist for class {class_level}",
        ))
        return _finalize(report)

    syl, parse_err = _load(path)
    if parse_err is not None:
        report.issues.append(Issue("error", "file", parse_err))
        return _finalize(report)
    if syl is None or not isinstance(syl, dict):
        report.issues.append(Issue("error", "file", "syllabus root is not a JSON object"))
        return _finalize(report)

    # Class-level + filename consistency.
    declared = syl.get("class_level")
    if declared is not None and declared != class_level:
        report.issues.append(Issue(
            "warning", "class_level",
            f"filename implies class {class_level} but JSON declares class_level={declared!r}",
        ))

    # Required top-level keys.
    if "cycles" not in syl:
        report.issues.append(Issue("error", "cycles", "missing 'cycles' array"))
        return _finalize(report)
    cycles = syl["cycles"]
    if not isinstance(cycles, list):
        report.issues.append(Issue("error", "cycles", "'cycles' must be an array"))
        return _finalize(report)
    if not cycles:
        report.issues.append(Issue("error", "cycles", "'cycles' is empty"))
        return _finalize(report)

    # Walk each cycle.
    parsed_cycles: list[tuple[int, str, date, date, dict[str, Any]]] = []
    for i, c in enumerate(cycles):
        loc = f"cycles[{i}]"
        if not isinstance(c, dict):
            report.issues.append(Issue("error", loc, "cycle entry is not an object"))
            continue
        name = c.get("name")
        if not name or not isinstance(name, str):
            report.issues.append(Issue("error", f"{loc}.name", "missing or non-string name"))
            continue

        start = _parse_iso(c.get("start"))
        end = _parse_iso(c.get("end"))
        if start is None:
            report.issues.append(Issue(
                "error", f"{loc}.start",
                f"start date not ISO YYYY-MM-DD: {c.get('start')!r}",
            ))
            continue
        if end is None:
            report.issues.append(Issue(
                "error", f"{loc}.end",
                f"end date not ISO YYYY-MM-DD: {c.get('end')!r}",
            ))
            continue
        if end < start:
            report.issues.append(Issue(
                "error", loc,
                f"{name}: end {end.isoformat()} is before start {start.isoformat()}",
            ))

        topics = c.get("topics_by_subject", {})
        if not isinstance(topics, dict):
            report.issues.append(Issue(
                "error", f"{loc}.topics_by_subject",
                "must be an object mapping subject → topic list",
            ))
            topics = {}
        if not topics:
            report.issues.append(Issue(
                "warning", f"{loc}.topics_by_subject",
                f"{name}: no subjects defined",
            ))

        # Per-subject checks.
        for subj, topic_list in (topics or {}).items():
            sloc = f"{loc}.topics_by_subject[{subj!r}]"
            if not isinstance(topic_list, list):
                report.issues.append(Issue(
                    "error", sloc, "value must be an array of topic strings",
                ))
                continue
            if not topic_list:
                report.issues.append(Issue(
                    "warning", sloc, f"{subj}: empty topic list",
                ))
                continue
            seen: dict[str, int] = {}
            for j, t in enumerate(topic_list):
                tloc = f"{sloc}[{j}]"
                if not isinstance(t, str):
                    report.issues.append(Issue(
                        "error", tloc, f"topic must be a string, got {type(t).__name__}",
                    ))
                    continue
                if t != t.strip():
                    report.issues.append(Issue(
                        "warning", tloc, "topic has leading/trailing whitespace",
                    ))
                if not t.strip():
                    report.issues.append(Issue(
                        "error", tloc, "topic is empty / whitespace-only",
                    ))
                    continue
                norm = re.sub(r"\s+", " ", t.strip()).lower()
                if norm in seen:
                    report.issues.append(Issue(
                        "warning", tloc,
                        f"duplicate of {sloc}[{seen[norm]}] (after trim/case-fold): {t!r}",
                    ))
                else:
                    seen[norm] = j
                if _has_mojibake(t):
                    report.issues.append(Issue(
                        "warning", tloc,
                        "topic contains mojibake markers — likely a UTF-8 round-trip issue",
                    ))

        parsed_cycles.append((i, name, start, end, c))

    # Cross-cycle checks: order + overlap + gap.
    sorted_by_start = sorted(parsed_cycles, key=lambda t: t[2])
    if [c[0] for c in sorted_by_start] != [c[0] for c in parsed_cycles]:
        report.issues.append(Issue(
            "warning", "cycles",
            "cycles are not listed in chronological order of `start` date",
        ))

    for prev, curr in zip(sorted_by_start, sorted_by_start[1:]):
        _, prev_name, _, prev_end, _ = prev
        idx_curr, curr_name, curr_start, _, _ = curr
        if curr_start <= prev_end:
            report.issues.append(Issue(
                "error", f"cycles[{idx_curr}]",
                f"{curr_name} starts on {curr_start.isoformat()} which overlaps "
                f"{prev_name}'s end ({prev_end.isoformat()})",
            ))
        elif (curr_start - prev_end).days > 1:
            report.issues.append(Issue(
                "info", f"cycles[{idx_curr}]",
                f"{(curr_start - prev_end).days - 1}-day gap between "
                f"{prev_name} (ends {prev_end.isoformat()}) and "
                f"{curr_name} (starts {curr_start.isoformat()})",
            ))

    return _finalize(report)


def _finalize(report: ValidationReport) -> ValidationReport:
    counts: dict[str, int] = {"error": 0, "warning": 0, "info": 0}
    for i in report.issues:
        counts[i.severity] = counts.get(i.severity, 0) + 1
    report.summary = counts
    return report


def validate_all() -> list[dict[str, Any]]:
    """Validate every class_<N>_*.json under data/syllabus/."""
    out: list[dict[str, Any]] = []
    if not SYLLABUS_DIR.exists():
        return out
    seen: set[int] = set()
    for p in sorted(SYLLABUS_DIR.glob("class_*.json")):
        m = re.match(r"class_(\d+)_", p.name)
        if not m:
            continue
        cl = int(m.group(1))
        if cl in seen:
            continue
        seen.add(cl)
        out.append(validate(cl).to_dict())
    return out
