"""Mindspark sync — pull metrics, write to DB.

Two operating modes:

  recon mode (`mode='recon'`)
    Login, navigate to dashboard + topic-map URLs, listen on every
    XHR / fetch, dump the responses to data/mindspark_recon/<child>/
    *.json. Used the first time we run against a kid's account so we
    can build parsers from real data.

  metrics mode (`mode='metrics'`)
    Login, scrape only the parent-facing dashboard surfaces (topic
    map + recent sessions list), parse aggregates, upsert into
    `mindspark_session` and `mindspark_topic_progress`. Strict slow
    rate; no question content.

Always per-kid serial — never parallel across kids on the same Ei
infrastructure.
"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...config import REPO_ROOT, get_settings, mindspark_credentials_for
from ...db import get_async_session
from ...models import Child, MindsparkSession, MindsparkTopicProgress
from .client import (
    humanize_page,
    mindspark_session,
    navigate_via_link,
    slow_jitter,
)
from . import parsers as P


log = logging.getLogger(__name__)


# Pages we walk in metrics mode. Best-guess from the recon agent's
# spec; will be revised once we see real DOM. The slow_jitter() guard
# applies between every navigation.
DASHBOARD_PATH = "https://learn.mindspark.in/Student/student/home"
TOPIC_MAP_PATH = "https://learn.mindspark.in/Student/student/learn"
SESSION_HISTORY_PATH = "https://learn.mindspark.in/Student/student/content"


async def run_recon_for(child_id: int) -> dict[str, Any]:
    """Login as the kid, walk the parent-facing pages, capture every
    XHR response to disk. Use this BEFORE wiring the metrics-mode
    parsers — it lets us see the actual JSON shapes Ei serves.

    Output: data/mindspark_recon/<child_id>/<timestamp>/
              dashboard.html
              topic_map.html
              session_history.html
              xhr_<n>.json     (with response body for each XHR)
              urls.txt         (every URL the SPA hit)
    """
    out_dir = (
        REPO_ROOT
        / "data"
        / "mindspark_recon"
        / str(child_id)
        / datetime.now().strftime("%Y%m%d_%H%M%S")
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    captured: list[dict[str, Any]] = []

    async with mindspark_session(child_id=child_id) as page:
        # Listen on every response — keep only application/json + html.
        async def on_response(resp):
            try:
                ct = (resp.headers.get("content-type") or "").lower()
                if "application/json" not in ct:
                    return
                body = await resp.text()
                captured.append({
                    "url": resp.url,
                    "status": resp.status,
                    "body": body[:200_000],  # cap each entry
                })
            except Exception:
                pass

        page.on("response", on_response)

        # Walk the three pages with slow-rate guard between each.
        # Use referrer-chain navigation: dashboard is the entry, then
        # we click links inside it to reach topic-map and session-history
        # (falling back to goto-with-Referer if the SPA's link isn't
        # detectable). Each navigation gets humanize_page() — mouse
        # wiggle + scroll — afterwards.
        nav_plan = [
            ("dashboard", DASHBOARD_PATH, ()),
            ("topic_map", TOPIC_MAP_PATH, ("Learn", "Topic Map", "My Learning", "Subjects")),
            ("session_history", SESSION_HISTORY_PATH, ("Reports", "History", "My Activity", "Sessions")),
        ]
        is_first = True
        for label, url, hints in nav_plan:
            await slow_jitter()
            try:
                if is_first:
                    await page.goto(url, wait_until="networkidle", timeout=30_000)
                    await humanize_page(page)
                else:
                    await navigate_via_link(page, url, link_text_hints=hints)
            except Exception as e:
                log.warning("mindspark recon: %s nav failed: %s", label, e)
                is_first = False
                continue
            is_first = False
            try:
                html = await page.content()
            except Exception:
                html = ""
            (out_dir / f"{label}.html").write_text(html, encoding="utf-8")

        # Dump captured XHRs.
        for i, entry in enumerate(captured):
            (out_dir / f"xhr_{i:03d}.json").write_text(
                json.dumps(entry, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        (out_dir / "urls.txt").write_text(
            "\n".join(e["url"] for e in captured), encoding="utf-8",
        )

    return {
        "child_id": child_id,
        "out_dir": str(out_dir.relative_to(REPO_ROOT)),
        "captured_xhr_count": len(captured),
    }


async def run_metrics_for(
    session: AsyncSession,
    child: Child,
) -> dict[str, Any]:
    """Pull parent-facing metrics for a kid. Upserts into
    `mindspark_session` and `mindspark_topic_progress`.
    """
    if not get_settings().mindspark_enabled:
        return {"status": "disabled", "child_id": child.id}
    if mindspark_credentials_for(child.id) is None:
        return {"status": "no_creds", "child_id": child.id}

    sessions_inserted = 0
    sessions_updated = 0
    topics_upserted = 0

    async with mindspark_session(child_id=child.id) as page:
        await slow_jitter()
        try:
            await page.goto(DASHBOARD_PATH, wait_until="networkidle", timeout=30_000)
            await humanize_page(page)
        except Exception as e:
            log.warning("mindspark dashboard nav failed: %s", e)
            return {"status": "nav_fail", "child_id": child.id, "error": repr(e)}
        dashboard_html = await page.content()

        # Recent sessions list — try to parse from the dashboard HTML.
        # If the parser comes back empty, the page probably loads
        # sessions via XHR; we'll need the recon dump to find the
        # right endpoint. Until then, parsers.parse_sessions is a
        # best-guess no-op.
        sessions = P.parse_sessions(dashboard_html)
        for s in sessions:
            ext_id = str(s.get("external_id") or "").strip()
            if not ext_id:
                continue
            existing = (
                await session.execute(
                    select(MindsparkSession).where(
                        MindsparkSession.child_id == child.id,
                        MindsparkSession.external_id == ext_id,
                    )
                )
            ).scalar_one_or_none()
            if existing is None:
                row = MindsparkSession(child_id=child.id, external_id=ext_id)
                session.add(row)
                sessions_inserted += 1
            else:
                row = existing
                sessions_updated += 1
            row.subject = s.get("subject")
            row.topic_name = s.get("topic_name")
            row.started_at = s.get("started_at")
            row.ended_at = s.get("ended_at")
            row.duration_sec = s.get("duration_sec")
            row.questions_total = s.get("questions_total")
            row.questions_correct = s.get("questions_correct")
            row.accuracy_pct = s.get("accuracy_pct")
            row.raw_json = json.dumps(s, default=str, ensure_ascii=False)

        await slow_jitter()
        try:
            await navigate_via_link(
                page,
                TOPIC_MAP_PATH,
                link_text_hints=("Learn", "Topic Map", "My Learning", "Subjects"),
            )
        except Exception as e:
            log.warning("mindspark topic_map nav failed: %s", e)
            await session.commit()
            return {
                "status": "partial",
                "child_id": child.id,
                "sessions_inserted": sessions_inserted,
                "sessions_updated": sessions_updated,
                "topics_upserted": topics_upserted,
                "error": repr(e),
            }
        topic_html = await page.content()

        topics = P.parse_topic_progress(topic_html)
        for t in topics:
            subj = (t.get("subject") or "").strip()
            tname = (t.get("topic_name") or "").strip()
            if not subj or not tname:
                continue
            existing = (
                await session.execute(
                    select(MindsparkTopicProgress).where(
                        MindsparkTopicProgress.child_id == child.id,
                        MindsparkTopicProgress.subject == subj,
                        MindsparkTopicProgress.topic_name == tname,
                    )
                )
            ).scalar_one_or_none()
            if existing is None:
                row = MindsparkTopicProgress(
                    child_id=child.id,
                    subject=subj,
                    topic_name=tname,
                )
                session.add(row)
            else:
                row = existing
            row.topic_id = t.get("topic_id")
            row.accuracy_pct = t.get("accuracy_pct")
            row.questions_attempted = t.get("questions_attempted")
            row.time_spent_sec = t.get("time_spent_sec")
            row.mastery_level = t.get("mastery_level")
            row.last_activity_at = t.get("last_activity_at")
            row.raw_json = json.dumps(t, default=str, ensure_ascii=False)
            row.updated_at = datetime.now(tz=timezone.utc)
            topics_upserted += 1

    await session.commit()
    return {
        "status": "ok",
        "child_id": child.id,
        "sessions_inserted": sessions_inserted,
        "sessions_updated": sessions_updated,
        "topics_upserted": topics_upserted,
    }


async def run_metrics_all() -> dict[str, Any]:
    """Run metrics-mode for every kid that has Mindspark credentials
    set, serially. Returns per-kid summary."""
    if not get_settings().mindspark_enabled:
        return {"status": "disabled"}
    out: list[dict[str, Any]] = []
    async with get_async_session() as session:
        children = (await session.execute(select(Child))).scalars().all()
    for c in children:
        if mindspark_credentials_for(c.id) is None:
            out.append({"child_id": c.id, "status": "no_creds"})
            continue
        try:
            async with get_async_session() as session:
                r = await run_metrics_for(session, c)
                out.append(r)
        except Exception as e:
            log.exception("mindspark metrics failed for %s", c.display_name)
            out.append({"child_id": c.id, "status": "error", "error": repr(e)})
    return {"kids": out}
