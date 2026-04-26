"""Sunday-brief dry-run preview generator (Phase 16, iteration 1).

Iterates every kid in the DB, calls services.sunday_brief.build_brief()
for each, renders the result as markdown, and writes the file under
`data/sunday_brief_preview/<kid_slug>_<YYYY-MM-DD>.md`. No scheduling,
no UI, no dispatch — the parent reads the .md files manually before
approving the wiring.

Run:
    .venv/bin/python -m backend.scripts.sunday_brief_preview
        --no-llm              skip the local LLM polish; uses raw bullets
        --child <id>          render only one kid (id = 1 or 2)
        --date YYYY-MM-DD     pretend it's a different day (smoke testing)
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import date
from pathlib import Path

# Allow `from backend...` imports when invoked as a script.
ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from sqlalchemy import select  # noqa: E402

from backend.app.db import get_async_session  # noqa: E402
from backend.app.models import Child  # noqa: E402
from backend.app.services.sunday_brief import (  # noqa: E402
    build_brief,
    render_markdown,
)
from backend.app.util.paths import kid_slug  # noqa: E402
from backend.app.util.time import today_ist  # noqa: E402


OUT_DIR = ROOT / "data" / "sunday_brief_preview"


async def _main_async(args: argparse.Namespace) -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    if args.date:
        try:
            target_day = date.fromisoformat(args.date)
        except ValueError:
            print(f"--date must be YYYY-MM-DD, got {args.date!r}", file=sys.stderr)
            return 2
    else:
        target_day = today_ist()

    async with get_async_session() as session:
        q = select(Child).order_by(Child.id)
        children = (await session.execute(q)).scalars().all()
        if args.child is not None:
            children = [c for c in children if c.id == args.child]
            if not children:
                print(f"no child with id {args.child}", file=sys.stderr)
                return 2

        written: list[Path] = []
        for c in children:
            brief = await build_brief(
                session, c, today=target_day, use_llm=not args.no_llm,
            )
            md = render_markdown(brief)
            slug = kid_slug(c)
            out = OUT_DIR / f"{slug}_{brief.generated_for}.md"
            out.write_text(md, encoding="utf-8")
            written.append(out)

    for p in written:
        print(p)
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--no-llm", action="store_true",
        help="Skip local LLM polish; render the rule-built bullets as-is.",
    )
    parser.add_argument(
        "--child", type=int, default=None,
        help="Render only one kid by id.",
    )
    parser.add_argument(
        "--date", type=str, default=None,
        help="ISO date to render for (defaults to today_ist()).",
    )
    args = parser.parse_args()
    rc = asyncio.run(_main_async(args))
    sys.exit(rc)


if __name__ == "__main__":
    main()
