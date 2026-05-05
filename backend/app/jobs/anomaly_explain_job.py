"""Nightly anomaly auto-explainer.

Scans every kid for off-trend grades, runs the deterministic detector,
and pre-warms a Claude hypothesis for any new anomaly that doesn't
already have one cached on `veracross_items.llm_summary`. Also marks
fresh anomalies as `anomaly_status='open'` so the UI can distinguish
"never seen by parent" from "acknowledged".

Cadence: 02:30 IST nightly (after sync but before brief warmup at
02:00 IST has finished — they don't conflict, just stagger).

Cost guard: skips grades that already have a cached explanation
unless `force=True`. With ~5 new grades a week and ~30s/call, the
nightly budget is ~2 minutes of Opus time worst case.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from sqlalchemy import select

from ..db import get_async_session
from ..models import Child, VeracrossItem
from ..services.anomaly import (
    detect_anomalies_for_child,
    explain_grade_anomaly,
)

log = logging.getLogger(__name__)


async def run_anomaly_explainer(force: bool = False) -> dict[str, Any]:
    """Walk every kid → detect anomalies → explain the un-explained.

    Returns a per-kid + total breakdown. Safe to run any time; idempotent
    when force=False.
    """
    async with get_async_session() as session:
        children = (await session.execute(select(Child))).scalars().all()
        total_detected = 0
        total_explained = 0
        total_skipped_cached = 0
        total_failed = 0
        per_kid: list[dict[str, Any]] = []

        for c in children:
            anomalies = await detect_anomalies_for_child(session, c.id)
            kid_explained = 0
            kid_skipped = 0
            kid_failed = 0
            kid_marked_open = 0

            for a in anomalies:
                gid = a["grade_id"]
                # Mark as 'open' if status is None — first time we've
                # surfaced this flag. Don't overwrite dismissed/escalated.
                row = (
                    await session.execute(
                        select(VeracrossItem).where(VeracrossItem.id == gid)
                    )
                ).scalar_one_or_none()
                if row is not None and row.anomaly_status is None:
                    row.anomaly_status = "open"
                    row.anomaly_status_at = datetime.utcnow()
                    kid_marked_open += 1

                if not force and row is not None and row.llm_summary:
                    kid_skipped += 1
                    continue

                try:
                    res = await explain_grade_anomaly(
                        session, gid, force=force,
                    )
                    if res.get("explanation"):
                        kid_explained += 1
                    else:
                        kid_failed += 1
                except Exception as e:
                    log.warning(
                        "auto-explain failed for grade %s (kid %s): %s",
                        gid, c.id, e,
                    )
                    kid_failed += 1

            await session.commit()

            total_detected += len(anomalies)
            total_explained += kid_explained
            total_skipped_cached += kid_skipped
            total_failed += kid_failed
            per_kid.append({
                "child_id": c.id,
                "child_name": c.display_name,
                "detected": len(anomalies),
                "explained_now": kid_explained,
                "skipped_cached": kid_skipped,
                "failed": kid_failed,
                "marked_open": kid_marked_open,
            })

        log.info(
            "anomaly_explainer: detected=%d explained=%d cached=%d failed=%d",
            total_detected, total_explained, total_skipped_cached, total_failed,
        )
        return {
            "ok": True,
            "ran_at": datetime.utcnow().isoformat(),
            "totals": {
                "detected": total_detected,
                "explained_now": total_explained,
                "skipped_cached": total_skipped_cached,
                "failed": total_failed,
            },
            "per_kid": per_kid,
        }
