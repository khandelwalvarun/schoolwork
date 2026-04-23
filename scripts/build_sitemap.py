"""Produce a human-readable site-map + API-surface report from recon output.

Reads:
  recon/output/manifest.json
  recon/output/network/*.json
  recon/output/api/*.json (optional, from harvest_components.py)
  recon/output/api-index.json (optional)

Writes:
  recon/output/REPORT.md
"""

from __future__ import annotations

import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from urllib.parse import urlparse, parse_qs

try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
except Exception:
    pass

ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = ROOT / "recon" / "output"
NETWORK_DIR = OUTPUT_DIR / "network"
API_DIR = OUTPUT_DIR / "api"
MANIFEST = OUTPUT_DIR / "manifest.json"
API_INDEX = OUTPUT_DIR / "api-index.json"
REPORT = OUTPUT_DIR / "REPORT.md"


B64_ID_RE = re.compile(r"^[A-Za-z0-9+/=]{16,}$")


def classify_path(path: str) -> str:
    """Bucket a URL path into a pattern like /student/{id}/overview.
    Segment-by-segment so we don't accidentally normalize the school namespace.
    """
    parts = path.split("/")
    out_parts: list[str] = []
    for seg in parts:
        if not seg:
            out_parts.append(seg)
            continue
        if re.fullmatch(r"\d{4,}", seg):
            out_parts.append("{id}")
        elif re.fullmatch(
            r"[0-9A-F]{8}-[0-9A-F]{4}-[0-9A-F]{4}-[0-9A-F]{4}-[0-9A-F]{12}",
            seg,
            flags=re.I,
        ):
            out_parts.append("{guid}")
        elif B64_ID_RE.fullmatch(seg) and any(c in seg for c in "+/="):
            # base64-ish: only treat as opaque ID if it contains base64-only chars.
            out_parts.append("{b64}")
        else:
            out_parts.append(seg)
    return "/".join(out_parts)


def main() -> None:
    if not MANIFEST.exists():
        print("[error] manifest.json not found. Run recon first.")
        return

    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    pages = manifest.get("pages", [])

    # Group pages by classified URL pattern.
    pattern_pages: dict[str, list[dict]] = defaultdict(list)
    for p in pages:
        pattern_pages[classify_path(urlparse(p["final_url"]).path)].append(p)

    # Enumerate XHR endpoints seen across all captures.
    xhr_counter: Counter[str] = Counter()
    xhr_examples: dict[str, str] = {}
    for net_file in sorted(NETWORK_DIR.glob("*.json")):
        try:
            data = json.loads(net_file.read_text(encoding="utf-8"))
        except Exception:
            continue
        for entry in data:
            url = entry.get("url", "")
            if "portals.veracross.eu" not in url:
                continue
            parsed = urlparse(url)
            # Strip query for pattern counting but keep full URL as example.
            pattern = classify_path(parsed.path)
            xhr_counter[pattern] += 1
            if pattern not in xhr_examples:
                xhr_examples[pattern] = url

    # Harvested API bodies (if present).
    api_bodies: dict[str, dict] = {}
    if API_INDEX.exists():
        idx = json.loads(API_INDEX.read_text(encoding="utf-8"))
        for entry in idx:
            url = entry.get("url", "")
            body_path = entry.get("saved_body")
            if body_path and (ROOT / body_path).exists():
                try:
                    raw = (ROOT / body_path).read_text(encoding="utf-8")
                    if entry.get("content_type", "").lower().startswith("application/json") or raw.lstrip().startswith(("{", "[")):
                        api_bodies[url] = json.loads(raw)
                    else:
                        api_bodies[url] = {"_non_json_excerpt": raw[:300]}
                except Exception as e:
                    api_bodies[url] = {"_error": str(e)}

    # Compose report.
    lines: list[str] = []
    lines.append("# Veracross Parent Portal — Recon Report")
    lines.append("")
    lines.append(f"- Portal: `{manifest.get('portal')}`")
    lines.append(f"- Pages captured: **{len(pages)}**")
    lines.append(f"- Unique URL patterns: **{len(pattern_pages)}**")
    lines.append(f"- Unique Veracross XHR patterns: **{len(xhr_counter)}**")
    if api_bodies:
        lines.append(f"- API bodies harvested: **{len(api_bodies)}**")
    lines.append("")

    lines.append("## URL patterns (crawl)")
    lines.append("")
    lines.append("| Count | Pattern | Sample title |")
    lines.append("|------:|---------|--------------|")
    for pat, ps in sorted(pattern_pages.items(), key=lambda kv: (-len(kv[1]), kv[0])):
        sample = ps[0].get("title", "")[:60].replace("|", "/")
        lines.append(f"| {len(ps)} | `{pat}` | {sample} |")
    lines.append("")

    lines.append("## XHR / API endpoints (seen in browser)")
    lines.append("")
    lines.append("| Hits | Pattern | Example URL |")
    lines.append("|-----:|---------|-------------|")
    for pat, n in xhr_counter.most_common():
        ex = xhr_examples.get(pat, "").replace("|", "%7C")
        lines.append(f"| {n} | `{pat}` | `{ex}` |")
    lines.append("")

    if api_bodies:
        lines.append("## Harvested API bodies — top-level shape")
        lines.append("")
        for url, body in sorted(api_bodies.items()):
            lines.append(f"### `{url}`")
            if isinstance(body, dict):
                if "_non_json_excerpt" in body:
                    lines.append("```")
                    lines.append(body["_non_json_excerpt"])
                    lines.append("```")
                else:
                    keys = list(body.keys())
                    lines.append(f"- dict with {len(keys)} keys: `{keys[:20]}`")
            elif isinstance(body, list):
                lines.append(f"- list length {len(body)}")
                if body and isinstance(body[0], dict):
                    lines.append(f"- first-item keys: `{list(body[0].keys())[:20]}`")
            lines.append("")

    lines.append("## Student URLs")
    lines.append("")
    student_ids = sorted({
        m.group(1)
        for p in pages
        if (m := re.search(r"/student/(\d+)/", p["final_url"]))
    })
    lines.append(f"Discovered student IDs: `{student_ids}`")
    lines.append("")
    for sid in student_ids:
        lines.append(f"### Student {sid}")
        for p in pages:
            if f"/student/{sid}/" in p["final_url"]:
                tail = urlparse(p["final_url"]).path.split(f"/student/{sid}/", 1)[-1]
                lines.append(f"- `{tail}`  *(status={p['status']})*")
        lines.append("")

    lines.append("## Detail-type inventory")
    lines.append("")
    for kind in ("assignment", "event", "article"):
        matching = [p for p in pages if f"/detail/{kind}/" in p["final_url"]]
        lines.append(f"- `{kind}`: {len(matching)} captured")
    lines.append("")

    REPORT.write_text("\n".join(lines), encoding="utf-8")
    print(f"[ok] wrote {REPORT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
