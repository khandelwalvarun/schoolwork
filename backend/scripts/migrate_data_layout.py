"""One-shot migrator: move persistent state under data/ and rename attachments
to the human-readable per-kid layout.

Run with --dry-run first to see the plan; then re-run with --apply to perform
the moves. Idempotent: re-running after a successful migration is a no-op.

Does four things:
  1. Moves app.db (+ -wal/-shm) from <repo>/ to <repo>/data/
  2. Moves recon/storage_state.json to <repo>/data/storage_state.json
  3. For every attachments row, moves the file from data/attachments/<sha[:2]>/<sha><ext>
     to data/rawdata/<kid_slug>/attachments/<human-name>.<ext> and updates
     attachments.local_path in the DB.
  4. Moves flat data/spellbee/* into data/rawdata/<kid_slug>/spellbee/ — for
     now all lists go to the sole 4C kid (Samarth). If there are multiple 4C
     kids or none, the flat dir is left alone and a warning is printed.

Usage:
    uv run python backend/scripts/migrate_data_layout.py --dry-run
    uv run python backend/scripts/migrate_data_layout.py --apply
"""
from __future__ import annotations

import argparse
import shutil
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
DATA = ROOT / "data"
LEGACY_STORAGE_STATE = ROOT / "recon" / "storage_state.json"
LEGACY_ATTACHMENTS_ROOT = DATA / "attachments"
LEGACY_SPELLBEE_FLAT = DATA / "spellbee"


def _humanize_name(due_or_date: str | None, subject: str | None, title: str | None,
                   sha256: str, ext: str) -> str:
    # Inline slugify to avoid importing the app package (DB may not be at
    # its configured location yet during step 1).
    import re
    import unicodedata

    def slug(s: str, n: int = 40) -> str:
        if not s:
            return "misc"
        norm = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("ascii")
        t = re.sub(r"[^a-z0-9]+", "-", norm.lower()).strip("-")
        return (t[:n].rstrip("-") or "misc")

    def subj(s: str | None) -> str:
        if not s:
            return "misc"
        parts = s.strip().split(None, 1)
        rest = parts[1] if len(parts) == 2 and re.fullmatch(r"\d{1,2}[A-Za-z]?", parts[0]) else s
        return slug(rest)

    date = (due_or_date or "0000-00-00")[:10]
    s8 = sha256[:8]
    ext = ext.lower()
    if ext and not ext.startswith("."):
        ext = "." + ext
    return f"{date}_{subj(subject)}_{slug(title or '', 40)}_{s8}{ext}"


def _kid_slug(display_name: str, class_level: int, class_section: str | None) -> str:
    import re
    import unicodedata
    norm = unicodedata.normalize("NFKD", display_name or "").encode("ascii", "ignore").decode("ascii")
    name = re.sub(r"[^a-z0-9]+", "-", norm.lower()).strip("-")[:24] or f"child"
    section = (class_section or "").strip()
    return f"{name}_{section or class_level}"


def step_move_db(apply: bool) -> tuple[bool, str]:
    legacy = ROOT / "app.db"
    new = DATA / "app.db"
    if new.exists() and not legacy.exists():
        return False, "[db] already at data/app.db"
    if legacy.exists() and new.exists():
        return True, f"[db] FATAL: both {legacy} and {new} exist — pick one manually"
    if not legacy.exists() and not new.exists():
        return False, "[db] no app.db anywhere — fresh install?"
    plan = [f"[db] move {legacy.name} → data/{legacy.name}"]
    for suf in ("-wal", "-shm"):
        src = ROOT / f"app.db{suf}"
        if src.exists():
            plan.append(f"[db] move app.db{suf} → data/app.db{suf}")
    if apply:
        DATA.mkdir(parents=True, exist_ok=True)
        shutil.move(str(legacy), str(new))
        for suf in ("-wal", "-shm"):
            src = ROOT / f"app.db{suf}"
            if src.exists():
                shutil.move(str(src), str(DATA / f"app.db{suf}"))
    return False, "\n".join(plan)


def step_move_storage_state(apply: bool) -> tuple[bool, str]:
    new = DATA / "storage_state.json"
    if new.exists() and not LEGACY_STORAGE_STATE.exists():
        return False, "[storage_state] already at data/"
    if not LEGACY_STORAGE_STATE.exists():
        return False, "[storage_state] no recon/storage_state.json to move"
    if new.exists():
        return False, f"[storage_state] destination exists; leaving {LEGACY_STORAGE_STATE} alone"
    msg = f"[storage_state] move recon/storage_state.json → data/storage_state.json"
    if apply:
        DATA.mkdir(parents=True, exist_ok=True)
        shutil.move(str(LEGACY_STORAGE_STATE), str(new))
    return False, msg


def step_migrate_attachments(apply: bool) -> tuple[bool, str]:
    db_path = DATA / "app.db"  # after step 1 the DB is here
    if not db_path.exists():
        db_path = ROOT / "app.db"
    if not db_path.exists():
        return False, "[attachments] no DB to read; skipping"

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute("""
            SELECT a.id, a.item_id, a.child_id, a.local_path, a.filename, a.sha256,
                   i.title, i.subject, i.due_or_date, i.first_seen_at,
                   c.display_name, c.class_level, c.class_section
            FROM attachments a
            LEFT JOIN veracross_items i ON i.id = a.item_id
            LEFT JOIN children c ON c.id = COALESCE(a.child_id, i.child_id)
        """).fetchall()

        plan: list[str] = []
        moves: list[tuple[Path, Path, int]] = []  # (src, dst, attachment_id)
        skipped: list[str] = []
        for r in rows:
            lp = r["local_path"]
            if not lp:
                skipped.append(f"#{r['id']}: no local_path")
                continue
            src = (ROOT / lp).resolve()
            # If already under rawdata/ layout, skip.
            if "rawdata" in src.parts:
                continue
            ext = Path(r["filename"] or src.name).suffix
            date_iso = (r["due_or_date"] or (r["first_seen_at"] or "")[:10]) or None
            human = _humanize_name(
                due_or_date=date_iso,
                subject=r["subject"],
                title=r["title"] or r["filename"],
                sha256=r["sha256"] or "",
                ext=ext,
            )
            if not r["display_name"]:
                skipped.append(f"#{r['id']}: no child row; cannot resolve kid dir")
                continue
            kid = _kid_slug(r["display_name"], r["class_level"], r["class_section"])
            dst_dir = DATA / "rawdata" / kid / "attachments"
            dst = dst_dir / human
            plan.append(f"[att #{r['id']}] {src.relative_to(ROOT)} → data/rawdata/{kid}/attachments/{human}")
            moves.append((src, dst, r["id"]))

        if apply and moves:
            for src, dst, att_id in moves:
                dst.parent.mkdir(parents=True, exist_ok=True)
                if not src.exists():
                    plan.append(f"[att #{att_id}] WARNING: source missing: {src}")
                    continue
                if dst.exists() and dst.resolve() != src.resolve():
                    # same content? then just drop the src
                    if dst.stat().st_size == src.stat().st_size:
                        src.unlink()
                    else:
                        plan.append(f"[att #{att_id}] WARNING: dst exists with different size; skipped")
                        continue
                else:
                    shutil.move(str(src), str(dst))
                rel = dst.resolve().relative_to(ROOT)
                conn.execute("UPDATE attachments SET local_path = ? WHERE id = ?", (str(rel), att_id))
            conn.commit()
            # Clean up empty sha-bucket dirs.
            if LEGACY_ATTACHMENTS_ROOT.exists():
                for sub in list(LEGACY_ATTACHMENTS_ROOT.iterdir()):
                    if sub.is_dir() and not any(sub.iterdir()):
                        sub.rmdir()
                if not any(LEGACY_ATTACHMENTS_ROOT.iterdir()):
                    LEGACY_ATTACHMENTS_ROOT.rmdir()

        msg = "\n".join(plan) if plan else "[attachments] nothing to migrate"
        if skipped:
            msg += "\n" + "\n".join(skipped)
        return False, msg
    finally:
        conn.close()


def step_migrate_spellbee(apply: bool) -> tuple[bool, str]:
    if not LEGACY_SPELLBEE_FLAT.exists():
        return False, "[spellbee] no flat data/spellbee/ to migrate"
    db_path = DATA / "app.db"
    if not db_path.exists():
        db_path = ROOT / "app.db"
    if not db_path.exists():
        return False, "[spellbee] no DB to identify kids; skipping"
    conn = sqlite3.connect(str(db_path))
    try:
        # The flat legacy dir is only in use by 4C kids. If we have exactly one
        # 4C kid, migrate there; else leave alone.
        fours = conn.execute(
            "SELECT id, display_name, class_level, class_section FROM children WHERE class_level = 4"
        ).fetchall()
        files = [p for p in LEGACY_SPELLBEE_FLAT.iterdir() if p.is_file()]
        if not files:
            if apply and LEGACY_SPELLBEE_FLAT.exists() and not any(LEGACY_SPELLBEE_FLAT.iterdir()):
                LEGACY_SPELLBEE_FLAT.rmdir()
            return False, "[spellbee] flat dir is empty; removed"
        if len(fours) != 1:
            return False, f"[spellbee] {len(files)} flat file(s) but {len(fours)} class-4 kids; manual decision needed"
        kid = fours[0]
        kid_slug = _kid_slug(kid[1], kid[2], kid[3])
        dst_dir = DATA / "rawdata" / kid_slug / "spellbee"
        plan = [f"[spellbee] move {len(files)} file(s) → data/rawdata/{kid_slug}/spellbee/"]
        if apply:
            dst_dir.mkdir(parents=True, exist_ok=True)
            for f in files:
                shutil.move(str(f), str(dst_dir / f.name))
            if not any(LEGACY_SPELLBEE_FLAT.iterdir()):
                LEGACY_SPELLBEE_FLAT.rmdir()
        return False, "\n".join(plan)
    finally:
        conn.close()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--apply", action="store_true", help="actually perform the moves")
    ap.add_argument("--dry-run", action="store_true", help="print plan only (default)")
    args = ap.parse_args()
    apply = args.apply
    if not apply and not args.dry_run:
        print("(defaulting to --dry-run; pass --apply to perform moves)")

    print(f"repo root: {ROOT}")
    print(f"data dir:  {DATA}")
    print()

    for step in (step_move_db, step_move_storage_state, step_migrate_attachments, step_migrate_spellbee):
        fatal, msg = step(apply)
        print(msg)
        print()
        if fatal:
            print("aborting (fatal).")
            return 2

    if apply:
        print("done.")
    else:
        print("dry-run complete. re-run with --apply to perform.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
