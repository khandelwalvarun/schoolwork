"""Extract a class syllabus PDF into structured JSON via Claude.

Usage:
    uv run python scripts/parse_syllabus.py --class 4 --pdf path/to/class4.pdf
    uv run python scripts/parse_syllabus.py --class 6 --pdf path/to/class6.pdf

Outputs:
    data/syllabus/class_{level}_2026-27.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from anthropic import AsyncAnthropic

SYSTEM = """You are extracting a school syllabus PDF into a strict JSON schema.

Output JSON with this exact shape:
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
        "Mathematics": ["..."],
        "Hindi": ["..."]
      }
    }
  ]
}

Rules:
- Use ISO dates. If only month+year are given, pick the 1st / last of the month.
- Subject names: use the exact names the syllabus uses (e.g. "Mathematics" not "Maths").
- Topics: keep verbatim phrasings where possible; trim whitespace.
- If the PDF doesn't divide the year into cycles, emit one cycle covering the whole year.
- Output ONLY the JSON — no prose, no markdown fences.
"""


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--class", dest="class_level", type=int, required=True)
    parser.add_argument("--pdf", type=Path, required=True)
    parser.add_argument(
        "--model", default=os.environ.get("ANTHROPIC_MODEL_SYLLABUS", "claude-opus-4-7")
    )
    args = parser.parse_args()

    if not args.pdf.exists():
        print(f"error: {args.pdf} does not exist", file=sys.stderr)
        sys.exit(2)

    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        print("error: ANTHROPIC_API_KEY not set", file=sys.stderr)
        sys.exit(2)

    client = AsyncAnthropic(api_key=key)

    pdf_bytes = args.pdf.read_bytes()
    import base64
    b64 = base64.b64encode(pdf_bytes).decode("ascii")

    msg = await client.messages.create(
        model=args.model,
        max_tokens=8_000,
        system=SYSTEM,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "document",
                        "source": {
                            "type": "base64",
                            "media_type": "application/pdf",
                            "data": b64,
                        },
                    },
                    {
                        "type": "text",
                        "text": f"Extract class {args.class_level} syllabus. Return JSON only.",
                    },
                ],
            }
        ],
    )
    text = "".join(b.text for b in msg.content if getattr(b, "text", None)).strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:]
    data = json.loads(text)

    out_dir = Path(__file__).resolve().parent.parent / "data" / "syllabus"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"class_{args.class_level}_2026-27.json"
    out_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[ok] wrote {out_path}  ({len(data.get('cycles', []))} cycles)")


if __name__ == "__main__":
    asyncio.run(main())
