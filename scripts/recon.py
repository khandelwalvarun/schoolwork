"""Controlled recon crawler for the Veracross parent portal.

Goals:
  * Log in once, reuse the browser storage context across runs.
  * Slow, jittered breadth-first crawl of every internal link.
  * Capture per-page: rendered HTML, screenshot, network XHR/fetch calls,
    visible text snippet, and anchor-link inventory.
  * Write a manifest.json tying everything together so we can build a
    site map and identify real APIs vs. HTML-only surfaces.

Safety rules (hard-coded — do NOT weaken without talking to the user):
  * Only follows ``<a href>`` navigation. Never clicks buttons, submits
    forms, or fires JS handlers.
  * Stays inside the portal's path prefix.
  * Skips any link whose text or href looks like logout/sign-out/signout.
  * Skips mailto:/tel:/javascript: and obvious file downloads.
  * Rate-limited with a random delay between ``SCRAPER_MIN_DELAY_SEC`` and
    ``SCRAPER_MAX_DELAY_SEC`` between pages, applied *before* each nav.
  * Persists visited set + queue on disk so Ctrl-C is resumable.

Usage:
    uv run python scripts/recon.py                  # headed, resume if state exists
    uv run python scripts/recon.py --headless
    uv run python scripts/recon.py --fresh          # wipe state + cookies
    uv run python scripts/recon.py --max-pages 50   # smaller run
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import random
import re
import shutil
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse, urlunparse

from playwright.async_api import (
    BrowserContext,
    Page,
    Request,
    Response,
    TimeoutError as PWTimeout,
    async_playwright,
)
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, TimeElapsedColumn

# Force UTF-8 stdout on Windows so rich's output won't explode on non-ASCII.
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
SNAPSHOT_DIR = OUTPUT_DIR / "pages"
SCREENSHOT_DIR = OUTPUT_DIR / "screenshots"
STATE_PATH = OUTPUT_DIR / "crawl-state.json"
MANIFEST_PATH = OUTPUT_DIR / "manifest.json"
NETWORK_DIR = OUTPUT_DIR / "network"

LOGOUT_PATTERNS = re.compile(r"(logout|sign[-_]?out|signout)", re.IGNORECASE)
FILE_EXTENSIONS_SKIP = {
    ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
    ".zip", ".rar", ".7z", ".tar", ".gz",
    ".png", ".jpg", ".jpeg", ".gif", ".svg", ".ico", ".webp",
    ".mp3", ".mp4", ".mov", ".avi", ".wav",
}


@dataclass
class PageCapture:
    url: str
    final_url: str
    depth: int
    status: int | None
    title: str
    html_path: str
    screenshot_path: str
    network_path: str
    visible_text_preview: str
    anchors: list[dict[str, str]]
    discovered_at: float


@dataclass
class CrawlState:
    queue: list[tuple[str, int]] = field(default_factory=list)
    visited: set[str] = field(default_factory=set)
    captures: list[PageCapture] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "queue": self.queue,
            "visited": sorted(self.visited),
            "captures": [c.__dict__ for c in self.captures],
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "CrawlState":
        return cls(
            queue=[tuple(x) for x in d.get("queue", [])],  # type: ignore[misc]
            visited=set(d.get("visited", [])),
            captures=[PageCapture(**c) for c in d.get("captures", [])],
        )


def slugify_url(url: str) -> str:
    h = hashlib.sha1(url.encode("utf-8")).hexdigest()[:10]
    parsed = urlparse(url)
    tail = re.sub(r"[^A-Za-z0-9]+", "-", (parsed.path or "/").strip("/") or "root")[:60]
    return f"{tail or 'root'}-{h}"


def normalize_url(url: str) -> str:
    """Drop fragments, normalize trailing slashes for dedup."""
    parsed = urlparse(url)
    path = parsed.path or "/"
    if path.endswith("/") and path != "/":
        path = path.rstrip("/")
    return urlunparse((parsed.scheme, parsed.netloc, path, parsed.params, parsed.query, ""))


def is_in_scope(url: str, portal_prefix: str) -> bool:
    return url.startswith(portal_prefix)


def should_skip_link(href: str, text: str) -> str | None:
    """Return a reason string if link should be skipped, else None."""
    h = href.strip()
    if not h:
        return "empty-href"
    if h.startswith(("mailto:", "tel:", "javascript:", "#")):
        return "non-http-scheme"
    if LOGOUT_PATTERNS.search(h) or LOGOUT_PATTERNS.search(text):
        return "logout"
    parsed = urlparse(h)
    ext = Path(parsed.path).suffix.lower()
    if ext in FILE_EXTENSIONS_SKIP:
        return f"file-ext:{ext}"
    return None


async def jitter_sleep(settings) -> None:
    delay = random.uniform(settings.scraper_min_delay_sec, settings.scraper_max_delay_sec)
    await asyncio.sleep(delay)


async def detect_login_form(page: Page) -> bool:
    """Heuristic: page has a password input visible."""
    try:
        loc = page.locator("input[type=password]").first
        return await loc.is_visible(timeout=2000)
    except Exception:
        return False


async def perform_login(page: Page, username: str, password: str) -> None:
    """Best-effort login: finds username & password inputs, fills, submits."""
    console.log("[yellow]Login form detected — attempting to authenticate…[/]")

    # Username field candidates (name/id contains user/email/login)
    user_sel = (
        "input[type=email], input[name*='user' i], input[name*='email' i], "
        "input[id*='user' i], input[id*='email' i], input[name*='login' i]"
    )
    pass_sel = "input[type=password]"

    await page.locator(user_sel).first.fill(username)
    await page.locator(pass_sel).first.fill(password)

    # Prefer submit button inside form; fallback to Enter key.
    submit = page.locator(
        "button[type=submit], input[type=submit], button:has-text('Sign in'), "
        "button:has-text('Log in'), button:has-text('Login')"
    ).first
    try:
        if await submit.count() > 0:
            await submit.click()
        else:
            await page.locator(pass_sel).first.press("Enter")
    except Exception as e:
        console.log(f"[red]Submit click failed: {e}; falling back to Enter key[/]")
        await page.locator(pass_sel).first.press("Enter")

    try:
        await page.wait_for_load_state("networkidle", timeout=30_000)
    except PWTimeout:
        console.log("[yellow]networkidle timed out post-login; continuing anyway[/]")


async def extract_anchors(page: Page) -> list[dict[str, str]]:
    """Return every <a> on the page with absolute href + visible text."""
    return await page.evaluate(
        """() => Array.from(document.querySelectorAll('a[href]')).map(a => ({
            href: a.href,
            text: (a.innerText || a.textContent || '').trim().slice(0, 200),
            rel: a.getAttribute('rel') || '',
            target: a.getAttribute('target') || '',
        }))"""
    )


async def extract_text_preview(page: Page, limit: int = 2000) -> str:
    try:
        text = await page.evaluate("() => document.body ? document.body.innerText : ''")
        return (text or "")[:limit]
    except Exception:
        return ""


class NetworkRecorder:
    """Collect all non-navigation XHR/fetch requests for a page."""

    def __init__(self) -> None:
        self.entries: list[dict[str, Any]] = []
        self._responses: dict[str, Response] = {}

    def attach(self, page: Page) -> None:
        page.on("response", self._on_response)

    def detach(self, page: Page) -> None:
        page.remove_listener("response", self._on_response)

    def _on_response(self, response: Response) -> None:
        try:
            req = response.request
            rtype = req.resource_type
            if rtype not in {"xhr", "fetch"}:
                return
            self.entries.append({
                "url": req.url,
                "method": req.method,
                "resource_type": rtype,
                "status": response.status,
                "content_type": response.headers.get("content-type", ""),
                "request_headers": {k: v for k, v in req.headers.items() if k.lower() != "cookie"},
                "post_data": (req.post_data or "")[:2000] if req.post_data else None,
            })
        except Exception:
            pass

    async def attach_bodies(self, responses_to_fetch: int = 50) -> None:
        """(Unused placeholder — body fetching done inline when needed.)"""
        return


async def capture_page(
    page: Page,
    url: str,
    depth: int,
    settings,
) -> tuple[PageCapture | None, list[str]]:
    """Navigate to url, snapshot everything, return capture + in-scope anchors."""
    recorder = NetworkRecorder()
    recorder.attach(page)

    status_code: int | None = None

    async def on_response(resp: Response) -> None:
        nonlocal status_code
        if resp.url == url or resp.url == page.url:
            if status_code is None and resp.request.resource_type == "document":
                status_code = resp.status

    page.on("response", on_response)

    try:
        nav = await page.goto(url, wait_until="domcontentloaded", timeout=45_000)
        if nav is not None and status_code is None:
            status_code = nav.status
        try:
            await page.wait_for_load_state("networkidle", timeout=15_000)
        except PWTimeout:
            pass
    except PWTimeout:
        console.log(f"[red]Timeout navigating to {url}[/]")
        recorder.detach(page)
        page.remove_listener("response", on_response)
        return None, []
    except Exception as e:
        console.log(f"[red]Navigation error on {url}: {e}[/]")
        recorder.detach(page)
        page.remove_listener("response", on_response)
        return None, []

    final_url = page.url
    title = (await page.title()) or ""
    slug = slugify_url(final_url)

    html = await page.content()
    html_path = SNAPSHOT_DIR / f"{slug}.html"
    html_path.write_text(html, encoding="utf-8")

    screenshot_path = SCREENSHOT_DIR / f"{slug}.png"
    try:
        await page.screenshot(path=str(screenshot_path), full_page=True)
    except Exception as e:
        console.log(f"[yellow]Screenshot failed for {final_url}: {e}[/]")

    network_path = NETWORK_DIR / f"{slug}.json"
    network_path.write_text(json.dumps(recorder.entries, indent=2), encoding="utf-8")

    anchors = await extract_anchors(page)
    text_preview = await extract_text_preview(page)

    recorder.detach(page)
    page.remove_listener("response", on_response)

    in_scope: list[str] = []
    portal_prefix = settings.veracross_portal_url.rstrip("/")
    for a in anchors:
        href = a.get("href", "")
        text = a.get("text", "")
        if should_skip_link(href, text):
            continue
        norm = normalize_url(href)
        if is_in_scope(norm, portal_prefix):
            in_scope.append(norm)

    capture = PageCapture(
        url=url,
        final_url=final_url,
        depth=depth,
        status=status_code,
        title=title,
        html_path=str(html_path.relative_to(ROOT).as_posix()),
        screenshot_path=str(screenshot_path.relative_to(ROOT).as_posix()),
        network_path=str(network_path.relative_to(ROOT).as_posix()),
        visible_text_preview=text_preview,
        anchors=anchors,
        discovered_at=time.time(),
    )
    return capture, in_scope


def save_state(state: CrawlState) -> None:
    STATE_PATH.write_text(json.dumps(state.to_dict(), indent=2), encoding="utf-8")


def load_state() -> CrawlState:
    if STATE_PATH.exists():
        data = json.loads(STATE_PATH.read_text(encoding="utf-8"))
        return CrawlState.from_dict(data)
    return CrawlState()


def write_manifest(state: CrawlState, settings) -> None:
    by_path: dict[str, list[dict[str, Any]]] = {}
    for cap in state.captures:
        parsed = urlparse(cap.final_url)
        by_path.setdefault(parsed.path or "/", []).append({
            "url": cap.final_url,
            "title": cap.title,
            "depth": cap.depth,
            "status": cap.status,
        })

    manifest = {
        "portal": settings.veracross_portal_url,
        "captured_pages": len(state.captures),
        "unique_paths": len(by_path),
        "paths": by_path,
        "pages": [c.__dict__ for c in state.captures],
    }
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2), encoding="utf-8")


async def run(args: argparse.Namespace) -> None:
    settings = get_settings()
    portal_prefix = settings.veracross_portal_url.rstrip("/")

    for d in (RECON_DIR, USER_DATA_DIR, OUTPUT_DIR, SNAPSHOT_DIR, SCREENSHOT_DIR, NETWORK_DIR):
        d.mkdir(parents=True, exist_ok=True)

    if args.fresh:
        console.log("[yellow]--fresh: wiping prior state, cookies, and snapshots[/]")
        for d in (SNAPSHOT_DIR, SCREENSHOT_DIR, NETWORK_DIR):
            shutil.rmtree(d, ignore_errors=True)
            d.mkdir(parents=True, exist_ok=True)
        if STATE_PATH.exists():
            STATE_PATH.unlink()
        shutil.rmtree(USER_DATA_DIR, ignore_errors=True)
        USER_DATA_DIR.mkdir(parents=True, exist_ok=True)

    state = load_state()
    if not state.queue and not state.visited:
        state.queue.append((portal_prefix, 0))

    max_pages = args.max_pages or settings.recon_max_pages
    max_depth = args.max_depth or settings.recon_max_depth

    console.rule("[bold cyan]Veracross portal recon")
    console.print(f"Portal: {portal_prefix}")
    console.print(f"Max pages: {max_pages}   Max depth: {max_depth}")
    console.print(
        f"Rate limit: {settings.scraper_min_delay_sec}-{settings.scraper_max_delay_sec}s jittered"
    )
    console.print(f"Headed: {not args.headless}")
    console.print(f"Output: {OUTPUT_DIR}")

    async with async_playwright() as pw:
        context: BrowserContext = await pw.chromium.launch_persistent_context(
            user_data_dir=str(USER_DATA_DIR),
            headless=args.headless,
            user_agent=settings.scraper_user_agent,
            viewport={"width": 1440, "height": 900},
            locale="en-US",
            args=["--disable-blink-features=AutomationControlled"],
        )
        context.set_default_navigation_timeout(45_000)
        page = context.pages[0] if context.pages else await context.new_page()

        # Always start by hitting the portal root and handling login if needed.
        console.log(f"[cyan]Opening {portal_prefix}[/]")
        try:
            await page.goto(portal_prefix, wait_until="domcontentloaded", timeout=45_000)
        except PWTimeout:
            console.log("[red]Initial nav timed out — aborting[/]")
            await context.close()
            return

        try:
            await page.wait_for_load_state("networkidle", timeout=15_000)
        except PWTimeout:
            pass

        if await detect_login_form(page):
            await perform_login(page, settings.veracross_username, settings.veracross_password)
            if await detect_login_form(page):
                console.log("[red]Still on login form after submit. Check credentials / MFA.[/]")
                console.log(
                    f"[red]Current URL: {page.url}   Title: {await page.title()}[/]"
                )
                await context.close()
                return
            console.log("[green]Login appears successful.[/]")
        else:
            console.log("[green]Already authenticated (persistent cookies).[/]")

        # After login we may have been redirected elsewhere; re-seed queue from here too.
        post_login = normalize_url(page.url)
        if post_login.startswith(portal_prefix) and post_login not in state.visited:
            state.queue.insert(0, (post_login, 0))

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            TextColumn("  visited: {task.fields[visited]}"),
            TextColumn("  queued: {task.fields[queued]}"),
            TimeElapsedColumn(),
            console=console,
        ) as progress:
            task = progress.add_task(
                "Crawling…",
                visited=len(state.visited),
                queued=len(state.queue),
                total=None,
            )

            while state.queue and len(state.visited) < max_pages:
                url, depth = state.queue.pop(0)
                url = normalize_url(url)
                if url in state.visited:
                    continue
                if depth > max_depth:
                    continue
                if not is_in_scope(url, portal_prefix):
                    continue

                state.visited.add(url)
                progress.update(
                    task,
                    description=f"[cyan]->[/] depth={depth}  {url}",
                    visited=len(state.visited),
                    queued=len(state.queue),
                )

                await jitter_sleep(settings)

                capture, new_links = await capture_page(page, url, depth, settings)
                if capture is None:
                    save_state(state)
                    continue

                state.captures.append(capture)

                # Detect accidental logout — if a capture lands us on a login form, stop.
                if await detect_login_form(page):
                    console.log("[red]Landed on a login form mid-crawl — session lost. Stopping.[/]")
                    save_state(state)
                    break

                for link in new_links:
                    if link in state.visited:
                        continue
                    if any(q[0] == link for q in state.queue):
                        continue
                    state.queue.append((link, depth + 1))

                save_state(state)
                progress.update(
                    task,
                    visited=len(state.visited),
                    queued=len(state.queue),
                )

        write_manifest(state, settings)
        console.rule("[bold green]Recon complete")
        console.print(f"Pages captured: {len(state.captures)}")
        console.print(f"Manifest: {MANIFEST_PATH}")
        await context.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--headless", action="store_true", help="Run without opening a window.")
    parser.add_argument("--fresh", action="store_true", help="Wipe state, cookies, and snapshots.")
    parser.add_argument("--max-pages", type=int, default=None)
    parser.add_argument("--max-depth", type=int, default=None)
    args = parser.parse_args()
    asyncio.run(run(args))


if __name__ == "__main__":
    main()
