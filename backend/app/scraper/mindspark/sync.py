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

    pages_captured: list[str] = []

    async with mindspark_session(child_id=child_id) as page:
        # We're authenticated AND the SPA has bootstrapped.
        # Mindspark's session is bound to the SPA router — any
        # `page.goto(url)` for an authenticated path triggers a
        # session-expired redirect back to /login. So we ONLY navigate
        # by clicking menu items, like a real user.

        async def _settle(extra_wait_sec: float = 4.0) -> None:
            try:
                await page.wait_for_load_state("networkidle", timeout=20_000)
            except Exception:
                pass
            # Heavy Angular SPAs render content into router-outlet AFTER
            # networkidle. Wait extra for component data fetches.
            await asyncio.sleep(extra_wait_sec)
            try:
                await humanize_page(page)
            except Exception:
                pass

        async def _capture(label: str) -> None:
            try:
                (out_dir / f"{label}.url.txt").write_text(page.url, encoding="utf-8")
                (out_dir / f"{label}.html").write_text(
                    await page.content(), encoding="utf-8",
                )
                pages_captured.append(label)
                log.info("mindspark recon: captured %s at %s", label, page.url)
            except Exception as e:
                log.warning("mindspark recon: capture failed for %s: %s", label, e)

        async def _click_menu(item_text: str) -> bool:
            """Click a sidebar/top-bar menu item by visible text. Returns
            True if the click landed."""
            try:
                # Strict text match first.
                loc = page.get_by_text(item_text, exact=True).first
                if await loc.count() > 0:
                    await loc.click(timeout=5_000)
                    return True
            except Exception:
                pass
            try:
                loc = page.locator(f'text="{item_text}"').first
                if await loc.count() > 0:
                    await loc.click(timeout=5_000)
                    return True
            except Exception:
                pass
            try:
                # Role-based link.
                loc = page.get_by_role("link", name=item_text)
                if await loc.count() > 0:
                    await loc.first.click(timeout=5_000)
                    return True
            except Exception:
                pass
            return False

        # Page 0 — settle on whatever post-login landed us (typically
        # /student/home). Wait long enough for the dashboard data
        # widgets to populate (Mindspark loads in the router-outlet
        # for several seconds after networkidle).
        await _settle(extra_wait_sec=6.0)
        await _capture("home_after_login")

        # Click through the menu items the parent cares about, in order.
        # Each: try-click → settle → capture → log.
        menu_walk = [
            ("Topics", "topics"),
            ("Homework", "homework"),
            ("Worksheets", "worksheets"),
            ("Rewards", "rewards"),
            ("Leaderboard", "leaderboard"),
        ]
        for menu_text, label in menu_walk:
            try:
                clicked = await _click_menu(menu_text)
            except Exception as e:
                log.warning("mindspark recon: click %r raised: %s", menu_text, e)
                clicked = False
            if not clicked:
                log.info("mindspark recon: no '%s' menu item visible; skipping", menu_text)
                continue
            await _settle(extra_wait_sec=4.0)
            await _capture(label)

    return {
        "child_id": child_id,
        "out_dir": str(out_dir.relative_to(REPO_ROOT)),
        "pages_captured": pages_captured,
    }


async def run_metrics_for(
    session: AsyncSession,
    child: Child,
) -> dict[str, Any]:
    """Pull parent-facing metrics for a kid. DOM-only — drives the
    SPA via menu clicks (the only navigation that doesn't trigger
    Mindspark's session-expiry redirect).

    Walks: home → click "Topics" → click "Leaderboard".
    Persists topics into `mindspark_topic_progress` (replace-on-update);
    the home/leaderboard summary lands as a daily snapshot row in
    `mindspark_session` keyed by external_id="snapshot_<YYYY-MM-DD>"
    so we get a sparkies-over-time history with no extra schema.
    """
    if not get_settings().mindspark_enabled:
        return {"status": "disabled", "child_id": child.id}
    if mindspark_credentials_for(child.id) is None:
        return {"status": "no_creds", "child_id": child.id}

    topics_upserted = 0
    home_summary: dict[str, Any] = {}
    leaderboard_summary: dict[str, Any] = {}

    async with mindspark_session(child_id=child.id) as page:
        # Settle on whatever post-login dropped us at (typically /home).
        try:
            await page.wait_for_load_state("networkidle", timeout=20_000)
        except Exception:
            pass
        await asyncio.sleep(6.0)
        try:
            await humanize_page(page)
        except Exception:
            pass
        try:
            home_html = await page.content()
            home_summary = P.parse_home_summary(home_html)
            log.info("mindspark home summary: %s", home_summary)
        except Exception as e:
            log.warning("mindspark home parse failed: %s", e)

        # Click "Topics" via the SPA menu — never goto, that breaks session.
        try:
            loc = page.get_by_text("Topics", exact=True).first
            if await loc.count() == 0:
                loc = page.get_by_role("link", name="Topics")
            await loc.click(timeout=5_000)
            try:
                await page.wait_for_load_state("networkidle", timeout=15_000)
            except Exception:
                pass
            await asyncio.sleep(4.0)
            await humanize_page(page)
            topics_html = await page.content()
        except Exception as e:
            log.warning("mindspark topics nav/parse failed: %s", e)
            topics_html = ""

        topics = P.parse_topics_page(topics_html)
        for t in topics:
            tname = (t.get("topic_name") or "").strip()
            if not tname:
                continue
            subj = t.get("subject") or "Mathematics"  # default; Mindspark Math is dominant
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
            row.accuracy_pct = t.get("accuracy_pct")
            # Mindspark exposes units (not raw question count); reuse field.
            row.questions_attempted = t.get("units_total")
            row.mastery_level = t.get("mastery_level")
            row.last_activity_at = datetime.now(tz=timezone.utc)
            row.raw_json = json.dumps(t, default=str, ensure_ascii=False)
            row.updated_at = datetime.now(tz=timezone.utc)
            topics_upserted += 1

        # Click "Leaderboard" → section rank + sparkies confirmation.
        try:
            loc = page.get_by_text("Leaderboard", exact=True).first
            if await loc.count() == 0:
                loc = page.get_by_role("link", name="Leaderboard")
            await loc.click(timeout=5_000)
            try:
                await page.wait_for_load_state("networkidle", timeout=15_000)
            except Exception:
                pass
            await asyncio.sleep(4.0)
            await humanize_page(page)
            leaderboard_html = await page.content()
            leaderboard_summary = P.parse_leaderboard_page(
                leaderboard_html, child_name=child.display_name,
            )
            log.info(
                "mindspark leaderboard: rank=%s sparkies=%s section_size=%s",
                leaderboard_summary.get("rank"),
                leaderboard_summary.get("sparkies"),
                leaderboard_summary.get("section_size"),
            )
        except Exception as e:
            log.warning("mindspark leaderboard nav/parse failed: %s", e)

    # Daily snapshot row — repurposes mindspark_session columns:
    # accuracy_pct = total sparkies, questions_correct = section rank,
    # questions_total = section size, topic_name = badge if any.
    today_iso = datetime.now(tz=timezone.utc).date().isoformat()
    ext_id = f"snapshot_{today_iso}"
    snap = (
        await session.execute(
            select(MindsparkSession).where(
                MindsparkSession.child_id == child.id,
                MindsparkSession.external_id == ext_id,
            )
        )
    ).scalar_one_or_none()
    if snap is None:
        snap = MindsparkSession(child_id=child.id, external_id=ext_id)
        session.add(snap)
    snap.subject = "Mathematics"
    snap.started_at = datetime.now(tz=timezone.utc)
    snap.questions_correct = leaderboard_summary.get("rank")
    snap.questions_total = leaderboard_summary.get("section_size")
    snap.accuracy_pct = home_summary.get("sparkies")
    snap.topic_name = leaderboard_summary.get("title")
    snap.raw_json = json.dumps({
        "home": home_summary,
        "leaderboard": leaderboard_summary,
    }, default=str, ensure_ascii=False)

    await session.commit()
    return {
        "status": "ok",
        "child_id": child.id,
        "topics_upserted": topics_upserted,
        "home": home_summary,
        "leaderboard": {
            k: v for k, v in leaderboard_summary.items() if k != "top_3"
        },
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
