"""Per-assignment "the ask in plain English" extractor.

Many Veracross assignment titles are cryptic ("Mathematics Worksheet",
"Chapter Review", "Speaking Skills - My Superpowers"). The body text
carries the actual ask but is multi-paragraph and prose-shaped — the
parent has to read it carefully to know what the kid is being asked
to do, what output is expected, and roughly how long it should take.

This service hands the title + body + subject to Claude (via the same
claude_cli backend used elsewhere) and gets back ONE crisp sentence
that's the actual ask, suitable for inline display in the AuditDrawer
just under the title.

Caching: the llm_summary column on veracross_items (added by Phase 22
for school-message summaries) is reused. If `llm_summary` is already
set we return it as-is. Pass `force=True` to recompute.

Failure mode: if Claude is unreachable or returns an empty string,
we return None and store nothing — the UI falls through to the raw
body. Better silence than a misleading summary.
"""
from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..llm.client import LLMClient
from ..models import VeracrossItem


log = logging.getLogger(__name__)


SYSTEM_PROMPT = """You compress a school assignment description into ONE crisp sentence.

You will receive:
  - subject (e.g. "6B English", "4C Hindi")
  - title (often vague, like "Speaking Skills - My Superpowers")
  - body (the actual ask, multi-paragraph)

Output: ONE plain-English sentence (≤ 25 words) that names the
concrete task in the imperative — what the kid is being asked to do.
Include format/output expectations if the body specifies them
("a 1-minute talk", "in three sentences", "from the textbook").
Include any deadline or page reference verbatim.

Do NOT:
  - Repeat the title verbatim
  - Add encouragement or commentary
  - Use exclamation marks
  - Invent details not in the body
  - Add "the kid is asked to" / "the assignment requires" framings —
    just write the imperative

Examples:

  title:   "Speaking Skills - My Superpowers"
  body:    "If you were a superhero, what would your superpower be —
           and why? Think about the things you're really good at…
           Come prepared to share your real-life superpowers and tell
           us (in 1 minute) what makes you a superhuman!"
  output:  "Prepare a 1-minute talk on a real-life 'superpower' you
           have and why."

  title:   "Spelling Bee Class 4 - 27 Apr"
  body:    "Learn the spelling for words from boxes marked in the
           English book. Test on Monday."
  output:  "Learn spellings of the marked-box words from the English
           book; test on Monday."

  title:   "मूल्यांकन"
  body:    "१) मातृभूमि (कविता) २) वर्ण विच्छेद ३) र के रूप ४) अनुस्वार और अनुनासिक"
  output:  "Be ready for the Hindi assessment covering the poem
           मातृभूमि plus 3 grammar topics: वर्ण विच्छेद, र के रूप,
           अनुस्वार और अनुनासिक."

Output only the sentence. No JSON, no quotes, no prefix.
"""


def _too_short_to_summarize(body: str | None) -> bool:
    if not body:
        return True
    s = body.strip()
    if len(s) < 30:
        return True
    return False


async def summarize_assignment(
    session: AsyncSession,
    item_id: int,
    *,
    force: bool = False,
) -> dict[str, Any]:
    """Generate (or return cached) 1-sentence summary for an assignment.

    Returns:
      {item_id, summary, cached: bool, llm_used: bool}

    The `summary` may be None when the body is too short to be worth
    summarising (the UI just shows the body raw in that case).
    """
    item = (
        await session.execute(
            select(VeracrossItem).where(VeracrossItem.id == item_id)
        )
    ).scalar_one_or_none()
    if item is None:
        raise ValueError(f"assignment {item_id} not found")
    if item.kind != "assignment":
        raise ValueError(
            f"item {item_id} is kind={item.kind!r}, not 'assignment'"
        )

    if not force and item.llm_summary:
        return {
            "item_id": item.id,
            "summary": item.llm_summary,
            "cached": True,
            "llm_used": False,
        }

    if _too_short_to_summarize(item.body):
        return {
            "item_id": item.id,
            "summary": None,
            "cached": False,
            "llm_used": False,
        }

    client = LLMClient()
    if not client.enabled():
        return {
            "item_id": item.id,
            "summary": None,
            "cached": False,
            "llm_used": False,
        }

    subject = item.subject or "—"
    title = (item.title or item.title_en or "").strip()
    body = (item.body or "").strip()

    prompt = (
        f"subject: {subject}\n"
        f"title: {title}\n"
        f"body: {body}"
    )
    try:
        resp = await client.complete(
            purpose="assignment_summary",
            system=SYSTEM_PROMPT,
            prompt=prompt,
            max_tokens=120,
        )
    except Exception as e:
        log.warning("assignment_summary LLM failed for item %s: %s", item_id, e)
        return {
            "item_id": item.id,
            "summary": None,
            "cached": False,
            "llm_used": False,
        }

    text = (resp.text or "").strip()
    # Strip wrapping quotes the model sometimes adds.
    if text and text[0] in ('"', "'") and text[-1] in ('"', "'"):
        text = text[1:-1].strip()
    # Hard cap at 280 chars defensively.
    if len(text) > 280:
        text = text[:277].rstrip() + "…"
    if not text:
        return {
            "item_id": item.id,
            "summary": None,
            "cached": False,
            "llm_used": True,
        }

    item.llm_summary = text
    await session.commit()
    return {
        "item_id": item.id,
        "summary": text,
        "cached": False,
        "llm_used": True,
    }


async def summarize_all_with_body(
    session: AsyncSession,
    *,
    force: bool = False,
    limit: int | None = None,
) -> dict[str, Any]:
    """Backfill — generate summaries for every assignment that has a
    body but no llm_summary yet. Useful as a one-shot after the body
    fix lands and the back-fill detail-pass populates a wave of bodies.
    """
    q = (
        select(VeracrossItem)
        .where(VeracrossItem.kind == "assignment")
        .where(VeracrossItem.body.isnot(None))
        .where(VeracrossItem.body != "")
    )
    if not force:
        q = q.where(VeracrossItem.llm_summary.is_(None))
    if limit is not None:
        q = q.limit(limit)
    rows = (await session.execute(q)).scalars().all()
    summarised = 0
    skipped = 0
    failed = 0
    for r in rows:
        try:
            out = await summarize_assignment(session, r.id, force=force)
            if out.get("summary"):
                summarised += 1
            else:
                skipped += 1
        except Exception as e:
            log.warning("backfill failed for %s: %s", r.id, e)
            failed += 1
    return {
        "scanned": len(rows),
        "summarised": summarised,
        "skipped": skipped,
        "failed": failed,
    }
