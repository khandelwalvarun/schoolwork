"""Download a class syllabus PDF from Drive, extract text, ask claude -p to
structure it into JSON, save to data/syllabus/class_{N}_2026-27.json.

Usage:
    uv run python backend/scripts/fetch_syllabus.py --class 4
    uv run python backend/scripts/fetch_syllabus.py --class 6
    uv run python backend/scripts/fetch_syllabus.py --all
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from pathlib import Path

import httpx
from pypdf import PdfReader

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from backend.app.llm.client import LLMClient
from backend.app.syllabus_links import SYLLABUS_DRIVE_IDS, drive_download_url

try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
except Exception:
    pass

ROOT = Path(__file__).resolve().parent.parent.parent
OUT_DIR = ROOT / "data" / "syllabus"
CACHE_DIR = ROOT / "data" / "syllabus" / ".cache"
OUT_DIR.mkdir(parents=True, exist_ok=True)
CACHE_DIR.mkdir(parents=True, exist_ok=True)


async def _download_drive_pdf(file_id: str, dest: Path) -> None:
    """Download a Drive file. Handles the 'virus scan' confirmation page for
    large files."""
    if dest.exists() and dest.stat().st_size > 1000:
        print(f"  (cached) {dest.name}")
        return
    url = drive_download_url(file_id)
    async with httpx.AsyncClient(follow_redirects=True, timeout=60.0) as c:
        r = await c.get(url)
        ct = r.headers.get("content-type", "")
        if "pdf" in ct.lower() or r.content[:4] == b"%PDF":
            dest.write_bytes(r.content)
            print(f"  downloaded {len(r.content)} bytes")
            return
        # Drive confirmation page — extract the confirm token.
        m = re.search(r'name="confirm"\s+value="([^"]+)"', r.text) or re.search(
            r'confirm=([^&"]+)', r.text
        )
        form_action = re.search(r'action="([^"]+download[^"]+)"', r.text)
        if form_action:
            confirm_url = form_action.group(1).replace("&amp;", "&")
        else:
            confirm_url = f"https://drive.usercontent.google.com/download?id={file_id}&export=download&confirm={m.group(1) if m else 't'}"
        r2 = await c.get(confirm_url)
        if r2.headers.get("content-type", "").lower().startswith("application/pdf") or r2.content[:4] == b"%PDF":
            dest.write_bytes(r2.content)
            print(f"  downloaded {len(r2.content)} bytes (after confirm)")
            return
        raise RuntimeError(f"Drive did not return a PDF for {file_id}; got {ct}")


def _extract_text(pdf_path: Path, max_pages: int | None = None) -> str:
    reader = PdfReader(str(pdf_path))
    pages = reader.pages[:max_pages] if max_pages else reader.pages
    chunks: list[str] = []
    for i, p in enumerate(pages):
        try:
            chunks.append(f"\n--- page {i+1} ---\n" + (p.extract_text() or ""))
        except Exception as e:
            chunks.append(f"\n--- page {i+1} (extract failed: {e}) ---\n")
    return "".join(chunks)


def _system_prompt() -> str:
    return """You are extracting a school syllabus PDF (plain-text dump) into a strict JSON schema.

Output EXACTLY this JSON shape, nothing else (no markdown fences, no prose):

{
  "school_year": "2026-27",
  "class_level": <int>,
  "cycles": [
    {
      "name": "LC1",
      "start": "2026-04-01",
      "end": "2026-06-15",
      "topics_by_subject": {
        "English": ["..."],
        "Mathematics": ["..."]
      }
    }
  ]
}

Rules:
- Use ISO dates. If only month+year given, pick 1st/last of month.
- Subject names: use the exact name (e.g. "Mathematics" not "Maths").
- Topics: keep verbatim phrasings; trim whitespace; one-line each.
- If the PDF doesn't split the year into cycles, emit one cycle covering the whole year named "Full Year".
- If cycles are named differently (Term 1, LC1, Quarter 1 etc.), prefer "LC1/LC2/LC3/LC4" for 4-cycle schools and "Term 1/2/3" for 3-term schools.
- Output ONLY the JSON. No prose. No backticks."""


def _strip_fences(s: str) -> str:
    s = s.strip()
    if s.startswith("```"):
        s = s.strip("`")
        if s.startswith("json\n"):
            s = s[5:]
        elif s.startswith("json"):
            s = s[4:]
    return s.strip()


async def process_class(class_level: int) -> Path:
    name = f"Class {class_level}"
    file_id = SYLLABUS_DRIVE_IDS.get(name)
    if not file_id:
        raise RuntimeError(f"No Drive ID for {name}")

    print(f"[{name}] drive id: {file_id}")
    pdf_path = CACHE_DIR / f"class_{class_level}.pdf"
    await _download_drive_pdf(file_id, pdf_path)

    text = _extract_text(pdf_path)
    print(f"[{name}] extracted {len(text)} chars from {pdf_path.name}")

    # Truncate if enormous — claude CLI has request-size limits.
    MAX_PROMPT_CHARS = 180_000
    truncated = False
    if len(text) > MAX_PROMPT_CHARS:
        text = text[:MAX_PROMPT_CHARS]
        truncated = True
        print(f"[{name}] truncated to {MAX_PROMPT_CHARS} chars")

    client = LLMClient()
    resp = await client.complete(
        purpose="syllabus_parse",
        model="claude-haiku-4-5",  # fast enough for structured extraction
        system=_system_prompt(),
        prompt=(
            f"Extract the syllabus for Class {class_level}. Below is the raw PDF text "
            + ("(truncated)." if truncated else "(complete).")
            + "\n\n===\n"
            + text
            + "\n===\n\nReturn JSON only."
        ),
        max_tokens=6000,
        extra_cache_key=f"cls{class_level}",
    )

    cleaned = _strip_fences(resp.text)
    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError as e:
        debug_path = OUT_DIR / f".last_raw_class_{class_level}.txt"
        debug_path.write_text(resp.text, encoding="utf-8")
        raise RuntimeError(f"claude returned non-JSON (saved to {debug_path}): {e}") from e

    out_path = OUT_DIR / f"class_{class_level}_2026-27.json"
    out_path.write_text(json.dumps(parsed, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[{name}] -> {out_path}  ({len(parsed.get('cycles', []))} cycles)")
    return out_path


async def main() -> None:
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--class", dest="class_level", type=int)
    group.add_argument("--all", action="store_true")
    args = parser.parse_args()

    targets = [4, 6] if args.all else [args.class_level]
    for n in targets:
        try:
            await process_class(n)
        except Exception as e:
            print(f"[Class {n}] FAILED: {e}")


if __name__ == "__main__":
    asyncio.run(main())
