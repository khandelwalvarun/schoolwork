"""Nightly 02:00 IST regeneration of the Sunday and PTM briefs.

Pre-warms `data/cached_briefs/` so the next morning's page load serves
the fresh brief instantly instead of waiting ~30s per kid for Claude.

Per kid:
  Sunday brief — services/sunday_brief.build_brief() + render_markdown
  PTM brief    — services/ptm_brief.build_ptm_brief() + render_markdown

Both kinds get JSON + MD written. Stale entries (>30 days old) are
pruned at the end of the run.

Failures are logged but never raise — one kid's brief failing must
not block the other kid or the next night.
"""
from __future__ import annotations

import logging

from sqlalchemy import select

from ..db import get_async_session
from ..models import Child
from ..services import cached_briefs as CB
from ..services import ptm_brief as PB
from ..services import sunday_brief as SB
from ..util.time import today_ist


log = logging.getLogger(__name__)


async def run_brief_warmup() -> dict[str, int]:
    """Iterate every kid, regenerate both briefs, write to disk cache,
    prune old entries. Returns a small summary dict for the log."""
    today = today_ist()
    log.info("brief warmup: starting for %s", today.isoformat())

    async with get_async_session() as session:
        children = (await session.execute(select(Child))).scalars().all()

    sunday_ok = 0
    sunday_fail = 0
    ptm_ok = 0
    ptm_fail = 0

    for c in children:
        # Sunday brief.
        try:
            async with get_async_session() as s:
                brief = await SB.build_brief(s, c, today=today)
            md = SB.render_markdown(brief)
            payload = brief.to_dict()
            slug = CB.child_slug_for(c.display_name, c.id)
            CB.write_brief("sunday", slug, today, payload, md)
            sunday_ok += 1
        except Exception:
            log.exception("sunday-brief warmup failed for %s", c.display_name)
            sunday_fail += 1

        # PTM brief.
        try:
            async with get_async_session() as s:
                brief = await PB.build_ptm_brief(s, c, today=today)
            md = PB.render_markdown(brief)
            payload = brief.to_dict()
            slug = CB.child_slug_for(c.display_name, c.id)
            CB.write_brief("ptm", slug, today, payload, md)
            ptm_ok += 1
        except Exception:
            log.exception("ptm-brief warmup failed for %s", c.display_name)
            ptm_fail += 1

    pruned = CB.prune_old()
    log.info(
        "brief warmup: done sunday_ok=%d sunday_fail=%d ptm_ok=%d ptm_fail=%d pruned=%d",
        sunday_ok, sunday_fail, ptm_ok, ptm_fail, pruned,
    )
    return {
        "sunday_ok": sunday_ok,
        "sunday_fail": sunday_fail,
        "ptm_ok": ptm_ok,
        "ptm_fail": ptm_fail,
        "pruned": pruned,
    }
