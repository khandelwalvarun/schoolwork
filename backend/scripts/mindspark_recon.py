"""Mindspark recon — login once and dump the JSON / HTML the SPA serves.

Run this BEFORE expecting metrics-mode parsers to work. Output lands in
data/mindspark_recon/<child_id>/<timestamp>/ with one JSON per XHR plus
the raw HTML of dashboard / topic-map / session-history pages.

Usage:
  MINDSPARK_USERNAME_1=tejas.khandelwal1 \\
  MINDSPARK_PASSWORD_1=noisycredit \\
  uv run python -m backend.scripts.mindspark_recon --child 1

Then look at data/mindspark_recon/1/<ts>/ — find the XHR endpoints
that return session data and topic progress, and tell me their URL +
shape so I can refine backend/app/scraper/mindspark/parsers.py.
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys

from backend.app.scraper.mindspark.sync import run_recon_for


def _check_env(child_id: int) -> None:
    keys = (f"MINDSPARK_USERNAME_{child_id}", f"MINDSPARK_PASSWORD_{child_id}")
    missing = [k for k in keys if not os.environ.get(k)]
    if missing:
        sys.stderr.write(
            f"ERROR: missing env vars: {', '.join(missing)}\n"
            f"  set these in .env or inline:\n"
            f"    MINDSPARK_USERNAME_{child_id}=…\n"
            f"    MINDSPARK_PASSWORD_{child_id}=…\n"
        )
        sys.exit(2)


async def _main(child_id: int) -> None:
    _check_env(child_id)
    out = await run_recon_for(child_id)
    print(f"recon done — wrote to {out['out_dir']}")
    print(f"captured {out['captured_xhr_count']} XHR responses")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--child", type=int, required=True,
                   help="child id (1=Tejas, 2=Samarth)")
    args = p.parse_args()
    asyncio.run(_main(args.child))
