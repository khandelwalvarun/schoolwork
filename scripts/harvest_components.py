"""Second-pass harvester: replay every unique XHR endpoint we discovered and save
the JSON body.

Reads recon/output/network/*.json, collects unique in-scope Veracross endpoints
(component/*/load_data and any other XHR hitting portals.veracross.eu), then
re-fetches each one via the already-authenticated Playwright context and saves
the response body to recon/output/api/<slug>.json alongside metadata.

Uses the same slow pacing as the crawler.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import random
import sys
from pathlib import Path
from urllib.parse import urlparse

from playwright.async_api import async_playwright
from rich.console import Console

try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    sys.stderr.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
except Exception:
    pass

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from schoolwork.config import get_settings  # noqa: E402

console = Console()
ROOT = Path(__file__).resolve().parent.parent
RECON_DIR = ROOT / "recon"
USER_DATA_DIR = RECON_DIR / "user-data"
OUTPUT_DIR = RECON_DIR / "output"
NETWORK_DIR = OUTPUT_DIR / "network"
API_DIR = OUTPUT_DIR / "api"
API_DIR.mkdir(parents=True, exist_ok=True)

INDEX_PATH = OUTPUT_DIR / "api-index.json"


def slug(url: str) -> str:
    h = hashlib.sha1(url.encode("utf-8")).hexdigest()[:10]
    parsed = urlparse(url)
    tail = (parsed.path or "/").strip("/").replace("/", "_")[:80]
    q = parsed.query.replace("&", "_").replace("=", "-")[:40]
    pieces = [tail or "root"]
    if q:
        pieces.append(q)
    pieces.append(h)
    return "_".join(pieces)


def discover_endpoints() -> list[str]:
    """Return sorted unique Veracross portal XHR URLs from recorded network logs."""
    seen: set[str] = set()
    for f in sorted(NETWORK_DIR.glob("*.json")):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        for entry in data:
            url = entry.get("url", "")
            if "portals.veracross.eu" not in url:
                continue
            if entry.get("method", "GET") != "GET":
                continue
            seen.add(url)
    return sorted(seen)


async def main() -> None:
    settings = get_settings()
    endpoints = discover_endpoints()
    console.rule("[bold cyan]Component harvest")
    console.print(f"Unique GET endpoints: {len(endpoints)}")
    if not endpoints:
        console.print("[yellow]No endpoints to harvest. Run recon first.[/]")
        return

    async with async_playwright() as pw:
        context = await pw.chromium.launch_persistent_context(
            user_data_dir=str(USER_DATA_DIR),
            headless=True,
            user_agent=settings.scraper_user_agent,
            viewport={"width": 1440, "height": 900},
            locale="en-US",
        )
        page = context.pages[0] if context.pages else await context.new_page()

        portal = settings.veracross_portal_url.rstrip("/")
        try:
            await page.goto(portal, wait_until="domcontentloaded", timeout=45_000)
            await page.wait_for_load_state("networkidle", timeout=15_000)
        except Exception:
            pass

        try:
            logged_out = await page.locator("input[type=password]").first.is_visible(timeout=2000)
        except Exception:
            logged_out = False
        if logged_out:
            console.print("[yellow]Session expired — logging back in…[/]")
            try:
                user_sel = (
                    "input[type=email], input[name*='user' i], input[name*='email' i], "
                    "input[id*='user' i], input[id*='email' i], input[name*='login' i]"
                )
                await page.locator(user_sel).first.fill(settings.veracross_username)
                await page.locator("input[type=password]").first.fill(settings.veracross_password)
                try:
                    submit = page.locator(
                        "button[type=submit], input[type=submit], "
                        "button:has-text('Sign in'), button:has-text('Log in')"
                    ).first
                    if await submit.count() > 0:
                        await submit.click(timeout=3000)
                    else:
                        await page.locator("input[type=password]").first.press("Enter")
                except Exception:
                    await page.locator("input[type=password]").first.press("Enter")
                try:
                    await page.wait_for_load_state("networkidle", timeout=30_000)
                except Exception:
                    pass
            except Exception as e:
                console.print(f"[red]Re-login failed: {e}. Aborting.[/]")
                await context.close()
                return
            try:
                still_out = await page.locator("input[type=password]").first.is_visible(timeout=2000)
            except Exception:
                still_out = False
            if still_out:
                console.print("[red]Re-login unsuccessful. Aborting.[/]")
                await context.close()
                return
            console.print("[green]Re-login succeeded.[/]")

        csrf = await page.evaluate(
            "() => document.querySelector('meta[name=csrf-token]')?.getAttribute('content')"
        )
        if not csrf:
            console.print("[red]Could not find CSRF token on root page. Aborting.[/]")
            await context.close()
            return
        console.print(f"CSRF token: {csrf[:16]}…")

        index: list[dict] = []
        for i, url in enumerate(endpoints, 1):
            delay = random.uniform(settings.scraper_min_delay_sec, settings.scraper_max_delay_sec)
            await asyncio.sleep(delay)

            console.print(f"[cyan]{i}/{len(endpoints)}[/] {url}")
            slug_name = slug(url)
            out_path = API_DIR / f"{slug_name}.json"

            try:
                resp = await context.request.get(
                    url,
                    headers={
                        "X-CSRF-Token": csrf,
                        "X-Requested-With": "XMLHttpRequest",
                        "Accept": "application/json, text/javascript, */*; q=0.01",
                        "Referer": portal,
                    },
                )
                status = resp.status
                ctype = resp.headers.get("content-type", "")
                body = await resp.text()
                record = {
                    "url": url,
                    "status": status,
                    "content_type": ctype,
                    "saved_body": str(out_path.relative_to(ROOT).as_posix()),
                }
                if "json" in ctype.lower():
                    try:
                        parsed = json.loads(body)
                        out_path.write_text(json.dumps(parsed, indent=2), encoding="utf-8")
                    except Exception:
                        out_path.write_text(body, encoding="utf-8")
                else:
                    out_path.write_text(body, encoding="utf-8")
                console.print(f"  -> {status} {ctype[:40]}  ({len(body)} bytes)")
                index.append(record)
            except Exception as e:
                console.print(f"  [red]error: {e}[/]")
                index.append({"url": url, "error": str(e)})

        INDEX_PATH.write_text(json.dumps(index, indent=2), encoding="utf-8")
        console.rule("[bold green]Harvest complete")
        console.print(f"Index: {INDEX_PATH}")
        await context.close()


if __name__ == "__main__":
    asyncio.run(main())
