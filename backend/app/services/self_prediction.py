"""Self-prediction band semantics + outcome derivation.

Bands map to score ranges (CBSE-typical thresholds, Vasant Valley
rubric-aware — keep aligned with topic_state.py):

  high    ≥ 85 %   ("I think I'll get a top grade")
  mid     70-85 %  ("I think I'll do okay")
  low     < 70 %   ("I think I'll struggle")
  %nn     numeric  ("I think I'll get exactly nn%") — within ±5 pts is "matched"

Outcomes:

  matched   actual lands in the predicted band (or within ±5 of a numeric)
  better    actual is above the band's upper edge
  worse     actual is below the band's lower edge

The pedagogy synthesis emphasised this loop as Zimmerman's
metacognition device — over weeks, repeated mismatches in one direction
tell the kid (and parent) something useful: "you tend to underestimate
yourself in math but overestimate in Hindi". A single test result is
not the signal; the streak is.
"""
from __future__ import annotations

from typing import Any


BAND_RANGES: dict[str, tuple[float, float]] = {
    "high":  (85.0, 101.0),
    "mid":   (70.0,  85.0),
    "low":   (0.0,   70.0),
}

NUMERIC_TOLERANCE = 5.0  # ± points around a numeric prediction = "matched"


def parse_band(prediction: str | None) -> tuple[float, float] | None:
    """Return (lower, upper) score band for a prediction string, or
    None if the input doesn't parse. Numeric predictions ("%85") return
    a tolerance band centered on the value."""
    if not prediction:
        return None
    s = prediction.strip().lower()
    if s in BAND_RANGES:
        return BAND_RANGES[s]
    if s.startswith("%"):
        try:
            n = float(s[1:])
        except ValueError:
            return None
        return (max(0.0, n - NUMERIC_TOLERANCE), min(100.0, n + NUMERIC_TOLERANCE))
    return None


def outcome_for(prediction: str | None, actual_pct: float | None) -> str | None:
    """Compute matched/better/worse. Returns None if either input is
    missing or unparseable."""
    if actual_pct is None:
        return None
    band = parse_band(prediction)
    if band is None:
        return None
    lo, hi = band
    if actual_pct >= hi:
        return "better"
    if actual_pct < lo:
        return "worse"
    return "matched"


def explain(prediction: str | None, actual_pct: float | None, outcome: str | None) -> str:
    """One-line plain-English summary for the UI tooltip."""
    if not prediction:
        return "No prediction recorded"
    if actual_pct is None:
        return f"Predicted '{prediction}'; grade not yet linked"
    band = parse_band(prediction) or (0, 100)
    lo, hi = band
    if outcome == "matched":
        return f"Predicted '{prediction}' ({lo:.0f}–{hi:.0f}%) — landed at {actual_pct:.0f}%, on target"
    if outcome == "better":
        return f"Predicted '{prediction}' ({lo:.0f}–{hi:.0f}%) — landed at {actual_pct:.0f}%, above"
    if outcome == "worse":
        return f"Predicted '{prediction}' ({lo:.0f}–{hi:.0f}%) — landed at {actual_pct:.0f}%, below"
    return f"Predicted '{prediction}'"


# Allowed values for input validation on the API.
VALID_BANDS = frozenset({"high", "mid", "low"})


def is_valid_prediction(prediction: str | None) -> bool:
    if not prediction:
        return False
    s = prediction.strip().lower()
    if s in VALID_BANDS:
        return True
    if s.startswith("%"):
        try:
            n = float(s[1:])
        except ValueError:
            return False
        return 0.0 <= n <= 100.0
    return False


def calibration_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate counts for a list of {prediction, outcome} rows.
    Returns {total, matched, better, worse, share_matched}.
    """
    total = sum(1 for r in rows if r.get("self_prediction") and r.get("self_prediction_outcome"))
    if total == 0:
        return {"total": 0, "matched": 0, "better": 0, "worse": 0, "share_matched": None}
    matched = sum(1 for r in rows if r.get("self_prediction_outcome") == "matched")
    better = sum(1 for r in rows if r.get("self_prediction_outcome") == "better")
    worse = sum(1 for r in rows if r.get("self_prediction_outcome") == "worse")
    return {
        "total": total,
        "matched": matched,
        "better": better,
        "worse": worse,
        "share_matched": round(matched / total, 2),
    }
