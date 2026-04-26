"""Mindspark Playwright client — login, storage-state reuse, slow rate.

Mirrors the existing Veracross client.py pattern but with stricter
delays (15-30s default vs Veracross's 3-6s) because we're a guest
on Ei's platform, not the school's portal.

Per-kid storage state lives at
  data/mindspark_state/<child_id>.json
which means re-running the scraper within ~1h reuses cookies + JWT
without re-auth. After expiry the next call falls through to a fresh
login.
"""
from __future__ import annotations

import asyncio
import json
import logging
import random
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

from playwright.async_api import (
    Browser, BrowserContext, Page, async_playwright,
)

from ...config import get_settings


log = logging.getLogger(__name__)


def _state_path_for(child_id: int) -> Path:
    s = get_settings()
    base = Path(s.mindspark_storage_state_dir)
    base.mkdir(parents=True, exist_ok=True)
    return base / f"{child_id}.json"


async def _slow_jitter() -> None:
    """Sleep 15-30s (or whatever's configured). Called after every
    navigation. The scraper is one in-flight request, no parallelism.
    """
    s = get_settings()
    lo = float(s.mindspark_min_delay_sec)
    hi = float(s.mindspark_max_delay_sec)
    if hi < lo:
        hi = lo
    await asyncio.sleep(random.uniform(lo, hi))


@asynccontextmanager
async def mindspark_session(
    child_id: int,
    *,
    headless: bool = True,
) -> AsyncIterator[Page]:
    """Open a Playwright page authenticated as the kid's Mindspark
    account. Reuses storage state if present and still valid;
    otherwise re-logs-in once.

    Usage:
        async with mindspark_session(child_id=1) as page:
            await page.goto("https://learn.mindspark.in/Student/student/learn")
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

    async with async_playwright() as p:
        browser: Browser = await p.chromium.launch(headless=headless)
        try:
            ctx_kwargs = {
                "user_agent": settings.scraper_user_agent,
            }
            if storage_state:
                ctx_kwargs["storage_state"] = storage_state
            ctx: BrowserContext = await browser.new_context(**ctx_kwargs)
            page = await ctx.new_page()

            # Probe: try a low-cost authenticated path. If it redirects
            # to login, fall through to fresh-login flow.
            await _slow_jitter()
            await page.goto(
                "https://learn.mindspark.in/Student/student/home",
                wait_until="domcontentloaded",
                timeout=30_000,
            )
            current = page.url
            if "login" in current.lower() or current.endswith("/onboard/login/en"):
                log.info("mindspark: storage state stale; logging in fresh for child %s", child_id)
                await _login(page, settings.mindspark_login_url, username, password)
                # Persist storage so the next run reuses the JWT.
                await ctx.storage_state(path=str(state_path))

            yield page

            # Refresh storage on the way out — captures any rotated
            # JWT / cookie touch from the session.
            try:
                await ctx.storage_state(path=str(state_path))
            except Exception:
                pass
        finally:
            await browser.close()


async def _login(page: Page, login_url: str, username: str, password: str) -> None:
    """Form login. Observed inputs (subject to change as Mindspark
    revises their SPA): name='loginid' for username, name='password'
    for password, submit button. Falls back to common alternates."""
    await _slow_jitter()
    await page.goto(login_url, wait_until="domcontentloaded", timeout=30_000)

    # Username field — try a few common selectors.
    for sel in (
        'input[name="loginid"]',
        'input[name="username"]',
        'input[name="email"]',
        'input[type="text"]',
    ):
        try:
            await page.fill(sel, username, timeout=2_500)
            break
        except Exception:
            continue
    else:
        raise RuntimeError("mindspark: could not find username field")

    for sel in (
        'input[name="password"]',
        'input[type="password"]',
    ):
        try:
            await page.fill(sel, password, timeout=2_500)
            break
        except Exception:
            continue
    else:
        raise RuntimeError("mindspark: could not find password field")

    # Submit.
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
        # Last resort — press Enter on the password field.
        await page.keyboard.press("Enter")

    # Wait for navigation away from the login page.
    try:
        await page.wait_for_url(
            lambda u: "login" not in u.lower(),
            timeout=15_000,
        )
    except Exception:
        # Could be a CAPTCHA or wrong-creds error. Caller should check
        # the page state via get_text / screenshot.
        log.warning("mindspark login: did not redirect away from /login")
    log.info("mindspark login: now at %s", page.url)


async def slow_jitter() -> None:
    """Public alias for callers in sync.py."""
    await _slow_jitter()
