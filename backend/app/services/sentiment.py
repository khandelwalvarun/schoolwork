"""Offline lexicon-based sentiment classifier.

No LLM call. No HTTP. Just a hand-curated word list tuned for the
language teachers actually use in school comments and progress notes.
The pedagogy synthesis explicitly cautioned against alerting on a
single comment — sentiment is reliably noisy at the per-comment level.
We surface a *trend* (rolling mean across recent comments), not the
raw scores, and never push notifications based on it.

Lexicon design choices:

  Positive cues   excellent, thoughtful, engaged, improved, careful,
                  participates, attentive, leader, kind, polite,
                  initiative, focused
  Negative cues   struggles, missed, distracted, careless, late,
                  rushed, behind, incomplete, off-task, disruptive,
                  forgot, lacks
  Intensifiers    very, really, extremely, consistently     (×1.4)
  Hedges          slightly, a little, occasionally, sometimes  (×0.6)
  Negators        not, never, no                            (flips next term)

Score is bounded to [-1, +1] per text; aggregated as a simple mean
over a rolling window (default 30 days). The trend is the *direction*
that matters; the absolute number is intentionally not surfaced as a
percentage to keep parents from grading the score itself.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Iterable


POSITIVE = {
    "excellent", "thoughtful", "engaged", "improved", "improving",
    "careful", "participates", "attentive", "leader", "kind",
    "polite", "initiative", "focused", "responsible", "creative",
    "enthusiastic", "diligent", "confident", "neat", "helpful",
    "well", "good", "great", "strong", "best", "wonderful",
    "perceptive", "insightful", "respectful", "punctual",
}

NEGATIVE = {
    "struggles", "struggling", "missed", "distracted", "careless",
    "late", "rushed", "behind", "incomplete", "off-task",
    "off", "disruptive", "forgot", "lacks", "weak", "poor",
    "messy", "untidy", "disengaged", "unfocused", "interrupts",
    "absent", "skipped", "loses", "noisy", "disturbing",
}

INTENSIFIERS = {"very", "really", "extremely", "consistently", "highly"}
HEDGES = {"slightly", "a", "little", "occasionally", "sometimes", "somewhat"}
NEGATORS = {"not", "never", "no", "without", "nor"}

WORD_RE = re.compile(r"[A-Za-z][A-Za-z'-]*")


@dataclass
class SentimentScore:
    score: float          # in [-1, +1]
    pos_hits: int
    neg_hits: int
    n_tokens: int


def score_text(text: str | None) -> SentimentScore:
    """Score one piece of text. Empty / non-Latin returns 0.0 with hits=0
    — the lexicon is English-only so we deliberately don't hallucinate
    sentiment on Hindi/Sanskrit comments."""
    if not text:
        return SentimentScore(0.0, 0, 0, 0)
    tokens = [m.group(0).lower() for m in WORD_RE.finditer(text)]
    if not tokens:
        return SentimentScore(0.0, 0, 0, 0)

    pos = 0.0
    neg = 0.0
    pos_hits = 0
    neg_hits = 0

    for i, tok in enumerate(tokens):
        if tok not in POSITIVE and tok not in NEGATIVE:
            continue
        weight = 1.0
        # Look back up to 2 tokens for intensifier/hedge/negator.
        flip = False
        for back in range(1, 3):
            if i - back < 0:
                break
            prev = tokens[i - back]
            if prev in NEGATORS:
                flip = not flip
            elif prev in INTENSIFIERS:
                weight *= 1.4
            elif prev in HEDGES:
                weight *= 0.6
        if tok in POSITIVE:
            if flip:
                neg += weight
                neg_hits += 1
            else:
                pos += weight
                pos_hits += 1
        else:  # negative
            if flip:
                pos += weight
                pos_hits += 1
            else:
                neg += weight
                neg_hits += 1

    raw = pos - neg
    # Normalise by hit count (not tokens) so a long bland comment with
    # one positive word doesn't get diluted to ~0.
    hits = pos_hits + neg_hits
    if hits == 0:
        return SentimentScore(0.0, 0, 0, len(tokens))
    score = max(-1.0, min(1.0, raw / max(hits, 1)))
    return SentimentScore(score, pos_hits, neg_hits, len(tokens))


def trend_points(
    items: Iterable[tuple[date, str]],
    *,
    today: date,
    window_days: int = 30,
    bucket_days: int = 7,
) -> list[dict[str, object]]:
    """Aggregate (date, text) items into a per-bucket mean-sentiment
    series. Default: 4 buckets of 7 days each = last 28 days.

    Each output point: {bucket_start (ISO), n, mean_score}.
    Buckets with no comments emit n=0 and mean_score=None — the UI can
    render them as gaps in the sparkline rather than zeros.
    """
    buckets: list[dict[str, object]] = []
    n_buckets = max(1, window_days // bucket_days)
    for b in range(n_buckets - 1, -1, -1):
        start = today - timedelta(days=(b + 1) * bucket_days - 1)
        buckets.append({
            "bucket_start": start.isoformat(),
            "scores": [],
        })
    items_list = list(items)
    for d, text in items_list:
        offset = (today - d).days
        if offset < 0 or offset >= window_days:
            continue
        bucket_idx = (window_days - 1 - offset) // bucket_days
        if 0 <= bucket_idx < len(buckets):
            sc = score_text(text)
            # Only count if the lexicon actually had a hit; bland
            # comments shouldn't sway the mean toward 0.
            if sc.pos_hits + sc.neg_hits > 0:
                buckets[bucket_idx]["scores"].append(sc.score)  # type: ignore

    out: list[dict[str, object]] = []
    for bk in buckets:
        scores = bk["scores"]  # type: ignore
        n = len(scores)
        mean = round(sum(scores) / n, 3) if n > 0 else None  # type: ignore
        out.append({
            "bucket_start": bk["bucket_start"],
            "n": n,
            "mean_score": mean,
        })
    return out
