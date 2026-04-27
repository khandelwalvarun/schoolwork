"""Mindspark Playwright client — login, storage-state reuse, slow rate.

Stealth posture (all 7 anti-automation fixes):

  1. headless=False by default (Mindspark sees a real, visible browser).
  2. tf-playwright-stealth applied to every context: patches
     navigator.webdriver, chrome.runtime, chrome.app, plugins, languages,
     fixes the WebGL/canvas fingerprint quirks, and a few dozen other
     headless-specific signals.
  3. Random viewport per session, picked from common Mac/PC sizes.
  4. Login fields typed char-by-char with 80-180ms per-key jitter
     (matches a real touch-typist).
  5. Random user-agent + accept-language rotation across a small pool
     of real, current Chrome strings, so fingerprint drifts between
     runs instead of being identical every time.
  6. Mouse-wiggle + scroll between page actions: real users look
     around when a page lands. We do too.
  7. Referrer-chain navigation: where possible we CLICK an internal
     link (`page.click(selector)`) rather than `goto(url)` so each
     navigation carries a Referer from the previous page, like a real
     SPA-driven session.

Per-kid storage state lives at
  data/mindspark_state/<child_id>.json
which means re-running the scraper within ~1h reuses cookies + JWT
without re-auth. After expiry the next call falls through to a fresh
login.
"""
from __future__ import annotations

import asyncio
import logging
import random
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

from playwright.async_api import (
    Browser, BrowserContext, Page, async_playwright,
)
from playwright_stealth import stealth_async

from ...config import get_settings


log = logging.getLogger(__name__)


# Pool of real Chrome user-agent strings (Mac + Windows, all recent).
# We pick one per browser context so successive runs look like
# different days from a slightly different machine.
_USER_AGENTS = [
    # macOS Sonoma + Chrome
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36",
    # Windows 10 + Chrome
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36",
]

# Common viewport sizes we randomize over. Real laptops + desktops.
_VIEWPORTS = [
    {"width": 1440, "height": 900},   # MacBook 13"
    {"width": 1512, "height": 982},   # MacBook 14"
    {"width": 1920, "height": 1080},  # FHD desktop
    {"width": 1366, "height": 768},   # common Win laptop
    {"width": 1600, "height": 900},   # widescreen laptop
]

# Languages — Indian English + Hindi mix, since the kid's location is India.
_ACCEPT_LANGUAGES = [
    "en-IN,en;q=0.9",
    "en-IN,en-US;q=0.9,en;q=0.8",
    "en-IN,en;q=0.9,hi;q=0.8",
]


def _state_path_for(child_id: int) -> Path:
    s = get_settings()
    base = Path(s.mindspark_storage_state_dir)
    base.mkdir(parents=True, exist_ok=True)
    return base / f"{child_id}.json"


async def _slow_jitter() -> None:
    """Sleep 15-30s (or whatever's configured). Called between page
    navigations. The scraper is one in-flight request, no parallelism.
    """
    s = get_settings()
    lo = float(s.mindspark_min_delay_sec)
    hi = float(s.mindspark_max_delay_sec)
    if hi < lo:
        hi = lo
    await asyncio.sleep(random.uniform(lo, hi))


async def _human_pause(short: bool = False) -> None:
    """Tiny pause inside a single action — between mouse moves,
    scrolls, char-by-char typing. Distinct from `_slow_jitter` which
    governs page-level pacing."""
    if short:
        await asyncio.sleep(random.uniform(0.08, 0.22))
    else:
        await asyncio.sleep(random.uniform(0.4, 1.2))


async def _human_mouse_wiggle(page: Page) -> None:
    """A real human nudges the mouse a few times after a page lands.
    We move to 2-4 random points within the viewport, with brief
    pauses. Tiny CPU cost; meaningful signal otherwise."""
    try:
        viewport = page.viewport_size
        if not viewport:
            return
        w = viewport["width"]
        h = viewport["height"]
        steps = random.randint(2, 4)
        for _ in range(steps):
            x = random.randint(int(w * 0.15), int(w * 0.85))
            y = random.randint(int(h * 0.15), int(h * 0.85))
            await page.mouse.move(x, y, steps=random.randint(8, 16))
            await _human_pause(short=True)
    except Exception:
        # Mouse moves are cosmetic; never let them break a scrape.
        pass


async def _human_scroll(page: Page) -> None:
    """Real users scroll through a page after it lands. We do 1-2
    scroll-downs followed by a half-scroll-up — a glance-and-skim
    pattern. All deltas are randomized."""
    try:
        for _ in range(random.randint(1, 2)):
            delta = random.randint(180, 480)
            await page.mouse.wheel(0, delta)
            await _human_pause()
        # Maybe scroll back up a little.
        if random.random() < 0.6:
            await page.mouse.wheel(0, -random.randint(80, 240))
            await _human_pause(short=True)
    except Exception:
        pass


async def humanize_page(page: Page) -> None:
    """Public helper: call after every navigation. Mouse wiggle +
    scroll + a beat. Imported by sync.py — keeps the human-emulation
    code in one place."""
    await _human_pause()
    await _human_mouse_wiggle(page)
    await _human_scroll(page)
    await _human_pause()


async def _human_type(page: Page, selector: str, value: str) -> None:
    """Fill a field char-by-char with per-key jitter (80-180ms)
    matching a real touch-typist's rhythm. Adds occasional ~250ms
    pauses to mimic glances at the screen."""
    await page.click(selector)
    await _human_pause(short=True)
    for ch in value:
        await page.keyboard.type(ch, delay=random.randint(80, 180))
        # Every ~10 chars, sometimes pause longer (looking up).
        if random.random() < 0.08:
            await asyncio.sleep(random.uniform(0.18, 0.36))


@asynccontextmanager
async def mindspark_session(
    child_id: int,
    *,
    headless: bool | None = None,
) -> AsyncIterator[Page]:
    """Open a Playwright page authenticated as the kid's Mindspark
    account, with the full stealth posture applied.

    `headless` defaults to False (real browser visible) — override by
    passing True if running on a server without a display.

    Usage:
        async with mindspark_session(child_id=1) as page:
            await navigate_via_link(page, "Topic Map")
            ...
    """
    from ...config import mindspark_credentials_for
    settings = get_settings()
    creds = mindspark_credentials_for(child_id)
    if creds is None:
        raise RuntimeError(
            f"no Mindspark credentials for child {child_id}; "
            f"set MINDSPARK_USERNAME_{child_id} + MINDSPARK_PASSWORD_{child_id} in .env"
        )
    username, password = creds

    state_path = _state_path_for(child_id)
    storage_state = str(state_path) if state_path.exists() else None

    if headless is None:
        # Default: visible browser (matches a real user). Override via
        # MINDSPARK_HEADLESS=true in env if you're running on a headless
        # box; we still try to keep tells minimal via stealth.
        import os
        env_val = os.environ.get("MINDSPARK_HEADLESS", "").strip().lower()
        headless = env_val in ("1", "true", "yes")

    user_agent = random.choice(_USER_AGENTS)
    viewport = random.choice(_VIEWPORTS)
    accept_lang = random.choice(_ACCEPT_LANGUAGES)

    async with async_playwright() as p:
        browser: Browser = await p.chromium.launch(
            headless=headless,
            args=[
                # Reduce common automation tells beyond stealth's
                # patches: disable the "Chrome is being controlled by
                # automated test software" infobar, etc.
                "--disable-blink-features=AutomationControlled",
                "--no-default-browser-check",
                "--no-first-run",
            ],
        )
        try:
            ctx_kwargs: dict = {
                "user_agent": user_agent,
                "viewport": viewport,
                "locale": accept_lang.split(",", 1)[0],
                "timezone_id": settings.tz,
                "extra_http_headers": {
                    "Accept-Language": accept_lang,
                },
            }
            if storage_state:
                ctx_kwargs["storage_state"] = storage_state
            ctx: BrowserContext = await browser.new_context(**ctx_kwargs)

            page = await ctx.new_page()
            # Apply stealth patches at the page level — patches
            # navigator.webdriver, chrome.runtime, plugins, languages,
            # permissions, WebGL/canvas fingerprint quirks, and other
            # headless-specific signals so this page reads as a real
            # interactive Chrome session.
            await stealth_async(page)

            # Probe: hit a low-cost authenticated path. If it 401s /
            # redirects to /login, fall through to fresh-login flow.
            await _slow_jitter()
            await page.goto(
                "https://learn.mindspark.in/Student/student/home",
                wait_until="domcontentloaded",
                timeout=30_000,
            )
            current = page.url
            if "login" in current.lower() or current.endswith("/onboard/login/en"):
                log.info(
                    "mindspark: storage state stale; logging in fresh for child %s",
                    child_id,
                )
                await _login(page, settings.mindspark_login_url, username, password)
                # Persist storage so the next run reuses the JWT.
                await ctx.storage_state(path=str(state_path))
            else:
                # Already on a logged-in page — let it settle, look around.
                await humanize_page(page)

            yield page

            # Refresh storage on the way out — captures any rotated
            # JWT / cookie touch from the session.
            try:
                await ctx.storage_state(path=str(state_path))
            except Exception:
                pass
        finally:
            await browser.close()


async def _login(
    page: Page, login_url: str, username: str, password: str,
) -> None:
    """Form login with human-like typing rhythm. Observed inputs
    (subject to change as Mindspark revises their SPA): `loginid`
    for username, `password` for password, submit button. Falls back
    to common alternates."""
    await _slow_jitter()
    await page.goto(login_url, wait_until="domcontentloaded", timeout=30_000)
    await humanize_page(page)

    # Username — try a few common selectors.
    user_sel = None
    for sel in (
        'input[name="loginid"]',
        'input[name="username"]',
        'input[name="email"]',
        'input[type="text"]',
    ):
        try:
            await page.wait_for_selector(sel, timeout=2_500, state="visible")
            user_sel = sel
            break
        except Exception:
            continue
    if user_sel is None:
        raise RuntimeError("mindspark: could not find username field")
    await _human_type(page, user_sel, username)
    await _human_pause()

    # Password — same probing.
    pass_sel = None
    for sel in (
        'input[name="password"]',
        'input[type="password"]',
    ):
        try:
            await page.wait_for_selector(sel, timeout=2_500, state="visible")
            pass_sel = sel
            break
        except Exception:
            continue
    if pass_sel is None:
        raise RuntimeError("mindspark: could not find password field")
    await _human_type(page, pass_sel, password)
    await _human_pause()

    # Submit — try the common submit selectors; fall back to Enter.
    submitted = False
    for sel in (
        'button[type="submit"]',
        'input[type="submit"]',
        'button:has-text("Login")',
        'button:has-text("Sign in")',
    ):
        try:
            await page.click(sel, timeout=2_500)
            submitted = True
            break
        except Exception:
            continue
    if not submitted:
        await page.keyboard.press("Enter")

    # Wait for navigation away from /login.
    try:
        await page.wait_for_url(
            lambda u: "login" not in u.lower(),
            timeout=15_000,
        )
    except Exception:
        log.warning("mindspark login: did not redirect away from /login")
    log.info("mindspark login: now at %s", page.url)
    # Settle on the new page — let any analytics SDK see normal
    # post-login activity (cursor moves, a scroll).
    await humanize_page(page)


async def navigate_via_link(
    page: Page,
    target_url: str,
    *,
    link_text_hints: tuple[str, ...] = (),
    fallback_goto: bool = True,
) -> None:
    """Navigate by CLICKING an internal link whose href matches the
    target (or whose visible text matches one of the hints), so the
    next request carries a Referer from the current page.

    Falls back to a regular goto() if no matching link is found —
    that's better than failing entirely. Anti-detection guarantee is
    only "best effort": deep-linking happens with a fallback log line
    so we can see when it fired.
    """
    # 1) try anchors with matching href.
    try:
        anchor = await page.query_selector(
            f'a[href="{target_url}"]'
        )
        if anchor is None:
            # Try partial path match.
            from urllib.parse import urlparse
            path = urlparse(target_url).path
            anchor = await page.query_selector(f'a[href*="{path}"]')
        if anchor is not None:
            await _human_mouse_wiggle(page)
            await anchor.click()
            try:
                await page.wait_for_url(
                    lambda u: target_url in u or u.startswith(target_url),
                    timeout=15_000,
                )
            except Exception:
                pass
            await humanize_page(page)
            return
    except Exception:
        pass

    # 2) try visible-text hints.
    for hint in link_text_hints:
        try:
            link = page.get_by_role("link", name=hint)
            if await link.count() > 0:
                await _human_mouse_wiggle(page)
                await link.first.click()
                await humanize_page(page)
                return
        except Exception:
            continue

    # 3) fallback — use goto with Referer set explicitly so the request
    # at least claims a chain.
    if fallback_goto:
        log.info(
            "navigate_via_link: no anchor for %s; falling back to goto",
            target_url,
        )
        prior_url = page.url
        await page.set_extra_http_headers({"Referer": prior_url})
        await page.goto(target_url, wait_until="domcontentloaded", timeout=30_000)
        # Clear the explicit referer so it doesn't pin to that value
        # for the rest of the session.
        await page.set_extra_http_headers({})
        await humanize_page(page)
    else:
        raise RuntimeError(f"no in-page link found for {target_url}")


async def slow_jitter() -> None:
    """Public alias for callers in sync.py."""
    await _slow_jitter()
