"""Seed the `children` table from the recon MyChildrenParent JSON snapshot.

Idempotent: upserts by veracross_id (=person_pk). Safe to re-run.

Usage:
    uv run python backend/scripts/seed_children.py
"""

from __future__ import annotations

import asyncio
import glob
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from sqlalchemy import select

from backend.app.db import get_async_session
from backend.app.models import Child


async def main() -> None:
    snapshot_paths = glob.glob(
        str(Path(__file__).resolve().parent.parent.parent
            / "recon/output/api/*MyChildrenParent*load_data*.json")
    )
    if not snapshot_paths:
        print("[error] No MyChildrenParent snapshot found. Run harvest_components.py first.")
        return

    data = json.loads(Path(snapshot_paths[0]).read_text(encoding="utf-8"))
    rows = data.get("children", [])
    if not rows:
        print("[error] No 'children' key in snapshot.")
        return

    # Hand-curated class info — MyChildrenParent doesn't include class level/section.
    class_map = {
        "103460": {"class_level": 6, "class_section": "6B"},  # Tejas
        "103609": {"class_level": 4, "class_section": "4C"},  # Samarth
    }

    async with get_async_session() as session:
        for row in rows:
            vc_id = str(row["person_pk"])
            name = row.get("first_name") or "?"
            cinfo = class_map.get(vc_id, {"class_level": 0, "class_section": None})

            existing = (
                await session.execute(
                    select(Child).where(Child.veracross_id == vc_id)
                )
            ).scalar_one_or_none()

            if existing:
                existing.display_name = name
                existing.class_level = cinfo["class_level"]
                existing.class_section = cinfo["class_section"]
                print(f"  updated: {name} (vc={vc_id}) -> {cinfo['class_section']}")
            else:
                c = Child(
                    display_name=name,
                    class_level=cinfo["class_level"],
                    class_section=cinfo["class_section"],
                    school="Vasant Valley",
                    veracross_id=vc_id,
                )
                session.add(c)
                print(f"  inserted: {name} (vc={vc_id}) -> {cinfo['class_section']}")

        await session.commit()

        rows_db = (await session.execute(select(Child))).scalars().all()
        print()
        print(f"children table now has {len(rows_db)} row(s):")
        for c in rows_db:
            print(f"  id={c.id}  {c.display_name}  {c.class_section}  vc={c.veracross_id}")


if __name__ == "__main__":
    asyncio.run(main())
