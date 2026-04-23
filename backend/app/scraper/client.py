"""Playwright-backed scraper client.

Reuses the persistent context from recon so cookies survive across runs.
Every external request is rate-limited with jitter; never more than one inflight.
Auto re-logs-in if the session has expired (detected via password-input visibility).
"""

from __future__ import annotations

import asyncio
import random
from contextlib import asynccontextmanager
from typing import Any
from urllib.parse import urljoin

from playwright.async_api import (
    BrowserContext,
    Page,
    Playwright,
    TimeoutError as PWTimeout,
    async_playwright,
)

from ..config import Settings, get_settings

EMBED_BASE = "https://portals-embed.veracross.eu"
DOCS_BASE = "https://documents.veracross.eu"


class ScraperClient:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self._pw: Playwright | None = None
        self._ctx: BrowserContext | None = None
        self._page: Page | None = None
        self._csrf: str | None = None
        self._lock = asyncio.Lock()

    async def __aenter__(self) -> "ScraperClient":
        self._pw = await async_playwright().start()
        self._ctx = await self._pw.chromium.launch_persistent_context(
            user_data_dir=self.settings.scraper_user_data_dir,
            headless=True,
            user_agent=self.settings.scraper_user_agent,
            viewport={"width": 1440, "height": 900},
            locale="en-US",
            args=["--disable-blink-features=AutomationControlled"],
        )
        self._ctx.set_default_navigation_timeout(45_000)
        self._page = self._ctx.pages[0] if self._ctx.pages else await self._ctx.new_page()
        await self._ensure_authenticated()
        return self

    async def __aexit__(self, *exc: Any) -> None:
        try:
            if self._ctx:
                await self._ctx.close()
        finally:
            if self._pw:
                await self._pw.stop()

    async def _sleep_jitter(self) -> None:
        lo = self.settings.scraper_min_delay_sec
        hi = self.settings.scraper_max_delay_sec
        await asyncio.sleep(random.uniform(lo, hi))

    async def _login(self) -> None:
        assert self._page is not None
        user_sel = (
            "input[type=email], input[name*='user' i], input[name*='email' i], "
            "input[id*='user' i], input[id*='email' i], input[name*='login' i]"
        )
        await self._page.locator(user_sel).first.fill(self.settings.veracross_username)
        await self._page.locator("input[type=password]").first.fill(self.settings.veracross_password)
        try:
            submit = self._page.locator(
                "button[type=submit], input[type=submit], "
                "button:has-text('Sign in'), button:has-text('Log in')"
            ).first
            if await submit.count() > 0:
                try:
                    await submit.click(timeout=3000)
                except Exception:
                    await self._page.locator("input[type=password]").first.press("Enter")
            else:
                await self._page.locator("input[type=password]").first.press("Enter")
        except Exception:
            await self._page.locator("input[type=password]").first.press("Enter")
        try:
            await self._page.wait_for_load_state("networkidle", timeout=30_000)
        except PWTimeout:
            pass

    async def _ensure_authenticated(self) -> None:
        assert self._page is not None
        portal = self.settings.veracross_portal_url.rstrip("/")
        await self._page.goto(portal, wait_until="domcontentloaded", timeout=45_000)
        try:
            await self._page.wait_for_load_state("networkidle", timeout=15_000)
        except PWTimeout:
            pass
        try:
            logged_out = await self._page.locator("input[type=password]").first.is_visible(
                timeout=2000
            )
        except Exception:
            logged_out = False
        if logged_out:
            await self._login()
            try:
                still_out = await self._page.locator("input[type=password]").first.is_visible(
                    timeout=2000
                )
            except Exception:
                still_out = False
            if still_out:
                raise RuntimeError("Login failed — check credentials or portal availability")

        csrf = await self._page.evaluate(
            "() => document.querySelector('meta[name=csrf-token]')?.getAttribute('content')"
        )
        if not csrf:
            raise RuntimeError("No CSRF token found after login")
        self._csrf = csrf

    async def get_html(self, url: str, wait_for: str | None = None) -> str:
        """Fetch a page's rendered HTML. Uses real navigation (handles JS-rendered content).

        `wait_for` — optional CSS selector to wait for before returning, improves reliability
        when the page hydrates client-side.
        """
        assert self._page is not None
        async with self._lock:
            await self._sleep_jitter()
            await self._page.goto(url, wait_until="domcontentloaded", timeout=45_000)
            try:
                await self._page.wait_for_load_state("networkidle", timeout=15_000)
            except PWTimeout:
                pass
            if wait_for:
                try:
                    await self._page.locator(wait_for).first.wait_for(
                        state="attached", timeout=10_000
                    )
                except PWTimeout:
                    pass
            # If we landed on a login form, re-authenticate and retry once.
            try:
                if await self._page.locator("input[type=password]").first.is_visible(timeout=500):
                    await self._ensure_authenticated()
                    await self._page.goto(url, wait_until="domcontentloaded", timeout=45_000)
                    try:
                        await self._page.wait_for_load_state("networkidle", timeout=15_000)
                    except PWTimeout:
                        pass
            except Exception:
                pass
            return await self._page.content()

    async def get_json(self, url: str) -> Any:
        """Fetch a JSON endpoint via the shared cookie store. Adds CSRF + XHR headers."""
        assert self._ctx is not None and self._csrf is not None
        async with self._lock:
            await self._sleep_jitter()
            resp = await self._ctx.request.get(
                url,
                headers={
                    "X-CSRF-Token": self._csrf,
                    "X-Requested-With": "XMLHttpRequest",
                    "Accept": "application/json, text/javascript, */*; q=0.01",
                    "Referer": self.settings.veracross_portal_url,
                },
                timeout=30_000,
            )
            if resp.status != 200:
                raise RuntimeError(f"GET {url} returned HTTP {resp.status}")
            return await resp.json()

    def main_portal_url(self, path: str) -> str:
        return urljoin(self.settings.veracross_portal_url.rstrip("/") + "/", path.lstrip("/"))

    def embed_planner_url(self, vc_id: str, school_year: int = 2026) -> str:
        return (
            f"{EMBED_BASE}/vasantvalleyschool/parent/planner"
            f"?p={vc_id}&school_year={school_year}"
        )

    def grade_report_url(self, class_id: str, grading_period: int) -> str:
        return (
            f"{DOCS_BASE}/vasantvalleyschool/grade_detail/{class_id}"
            f"?grading_period={grading_period}&key=_"
        )


@asynccontextmanager
async def scraper_session():
    client = ScraperClient()
    async with client:
        yield client
