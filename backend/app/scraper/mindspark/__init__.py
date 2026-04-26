"""Mindspark — narrow metrics-only scraper.

Scope contract (do not expand without re-confirming with the user):
  - per-session aggregate metrics (when, how long, accuracy)
  - per-topic progress snapshots (mastery, attempts, last activity)
  - NEVER question content, answer text, or pedagogical IP

Slow-rate guards: ≥15-30s between page navigations (configurable via
MINDSPARK_MIN_DELAY_SEC / MIN_MAX_DELAY_SEC). Daily cadence at most.
Per-kid storage_state reuse means we don't log in on every run; only
when the JWT (1-hour TTL) expires or the user signs out.
"""
