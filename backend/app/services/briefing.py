"""Digest builder. Composes a DigestData snapshot from the DB, asks the LLM for
a quantitative preamble (optional), and persists a Summary row.

Renderers in services/render.py turn DigestData into Telegram/Email/Web variants.
"""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_async_session
from ..llm.client import LLMClient
from ..config import get_settings
from ..models import Child, Summary, VeracrossItem
from . import queries as Q

IST = ZoneInfo("Asia/Kolkata")


@dataclass
class DigestAssignmentRow:
    subject: str | None
    title: str | None
    due: str | None
    type: str | None
    status: str | None
    external_id: str | None


@dataclass
class DigestGradeTrend:
    subject: str
    count: int
    latest: float
    avg: float
    sparkline: str
    arrow: str


@dataclass
class DigestKidSection:
    child_id: int
    name: str
    class_section: str | None
    overdue: list[DigestAssignmentRow] = field(default_factory=list)
    due_today: list[DigestAssignmentRow] = field(default_factory=list)
    upcoming: list[DigestAssignmentRow] = field(default_factory=list)
    overdue_by_subject: dict[str, int] = field(default_factory=dict)
    grade_trends: list[DigestGradeTrend] = field(default_factory=list)


@dataclass
class DigestData:
    generated_at_ist: str
    generated_for: str  # date string
    totals: dict[str, int]
    backlog_delta_48h: int | None
    kids: list[DigestKidSection]
    messages_last_7d: list[dict[str, Any]]
    preamble: str | None = None
    preamble_model: str | None = None


def _row(item: dict[str, Any]) -> DigestAssignmentRow:
    norm = item.get("normalized") or {}
    return DigestAssignmentRow(
        subject=item.get("subject"),
        title=item.get("title"),
        due=item.get("due_or_date"),
        type=norm.get("type"),
        status=item.get("status"),
        external_id=item.get("external_id"),
    )


async def build_digest_data(session: AsyncSession) -> DigestData:
    now_ist = datetime.now(tz=IST)
    today_iso = now_ist.date().isoformat()

    children = (await session.execute(select(Child).order_by(Child.id))).scalars().all()
    kids: list[DigestKidSection] = []
    totals = {"overdue": 0, "due_today": 0, "upcoming": 0}

    for c in children:
        overdue = await Q.get_overdue(session, c.id)
        due_today = await Q.get_due_today(session, c.id)
        upcoming = await Q.get_upcoming(session, c.id, days=14)
        subj_counter = Counter(
            (item.get("subject") or "Unknown") for item in overdue
        )
        trends_raw = await Q.get_grade_trends(session, c.id)
        trends = [
            DigestGradeTrend(
                subject=t["subject"], count=t["count"], latest=t["latest"],
                avg=t["avg"], sparkline=t["sparkline"], arrow=t["arrow"],
            )
            for t in trends_raw
        ]
        kids.append(
            DigestKidSection(
                child_id=c.id,
                name=c.display_name,
                class_section=c.class_section,
                overdue=[_row(x) for x in overdue],
                due_today=[_row(x) for x in due_today],
                upcoming=[_row(x) for x in upcoming],
                overdue_by_subject=dict(subj_counter),
                grade_trends=trends,
            )
        )
        totals["overdue"] += len(overdue)
        totals["due_today"] += len(due_today)
        totals["upcoming"] += len(upcoming)

    messages = await Q.get_messages(
        session, since=datetime.now(tz=timezone.utc) - timedelta(days=7)
    )

    # Backlog 48h delta — compare today's overdue to the last digest's overdue_total.
    delta: int | None = None
    prev = (
        await session.execute(
            select(Summary)
            .where(Summary.kind == "digest_4pm")
            .where(Summary.period_start < today_iso)
            .order_by(Summary.period_start.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if prev is not None:
        try:
            prev_totals = json.loads(prev.stats_json).get("totals", {})
            delta = totals["overdue"] - prev_totals.get("overdue", totals["overdue"])
        except Exception:
            pass

    return DigestData(
        generated_at_ist=now_ist.isoformat(),
        generated_for=today_iso,
        totals=totals,
        backlog_delta_48h=delta,
        kids=kids,
        messages_last_7d=messages,
    )


async def _fill_preamble(data: DigestData) -> None:
    """Ask Claude for a quantitative 3-5-sentence preamble. Silently skips if no API key."""
    client = LLMClient()
    if not client.enabled():
        return
    s = get_settings()
    prompt_path = Path(__file__).resolve().parent.parent / "llm" / "prompts" / "digest_preamble.md"
    try:
        system = prompt_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return
    facts = {
        "date": data.generated_for,
        "totals": data.totals,
        "backlog_delta_48h": data.backlog_delta_48h,
        "new_school_messages_count": len(data.messages_last_7d),
        "kids": [
            {
                "name": k.name,
                "class": k.class_section,
                "overdue_total": len(k.overdue),
                "overdue_by_subject": k.overdue_by_subject,
                "due_today": len(k.due_today),
                "upcoming_14d": len(k.upcoming),
            }
            for k in data.kids
        ],
    }
    user_prompt = (
        "Facts (JSON, authoritative — do not invent anything outside this):\n\n"
        + json.dumps(facts, ensure_ascii=False, indent=2)
    )
    try:
        resp = await client.complete(
            purpose="digest_preamble",
            model=s.claude_cli_model or None,
            system=system,
            prompt=user_prompt,
            max_tokens=400,
            extra_cache_key=data.generated_for,
        )
        data.preamble = resp.text.strip()
        data.preamble_model = resp.model
    except Exception:
        # Preamble failure is non-fatal; digest still renders without it.
        return


async def generate_and_store_digest(
    kind: str = "digest_4pm", llm: bool = True
) -> DigestData:
    async with get_async_session() as session:
        data = await build_digest_data(session)
        if llm:
            await _fill_preamble(data)

        # persist a summary row (content filled by renderer; here we store stats)
        from .render import render_text
        stats_json = json.dumps(
            {
                "totals": data.totals,
                "delta": data.backlog_delta_48h,
                "kid_counts": [
                    {
                        "name": k.name,
                        "overdue": len(k.overdue),
                        "due_today": len(k.due_today),
                        "upcoming": len(k.upcoming),
                    }
                    for k in data.kids
                ],
            },
            ensure_ascii=False,
        )
        content_md = render_text(data)

        existing = (
            await session.execute(
                select(Summary)
                .where(Summary.kind == kind)
                .where(Summary.period_start == data.generated_for)
            )
        ).scalar_one_or_none()
        if existing:
            existing.content_md = content_md
            existing.stats_json = stats_json
            existing.model_used = data.preamble_model or "none"
            existing.period_end = data.generated_for
        else:
            session.add(
                Summary(
                    kind=kind,
                    child_id=None,
                    period_start=data.generated_for,
                    period_end=data.generated_for,
                    content_md=content_md,
                    stats_json=stats_json,
                    model_used=data.preamble_model or "none",
                )
            )
        await session.commit()
        return data
