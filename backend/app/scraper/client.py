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
        self._browser: Any = None
        self._ctx: BrowserContext | None = None
        self._page: Page | None = None
        self._csrf: str | None = None
        self._storage_path: Any = None
        self._lock = asyncio.Lock()

    async def __aenter__(self) -> "ScraperClient":
        self._pw = await async_playwright().start()
        # Use a one-shot browser + new_context with storage_state loaded from disk.
        # storage_state captures cookies (including session-scoped ones like
        # _veracross_session) by value, so they survive browser restarts.
        # manual_login.py writes the state; scraper reads + updates it.
        self._browser = await self._pw.chromium.launch(
            headless=False,
            args=["--headless=new", "--disable-blink-features=AutomationControlled"],
        )
        ctx_kwargs: dict[str, Any] = dict(
            user_agent=self.settings.scraper_user_agent,
            viewport={"width": 1440, "height": 900},
            locale="en-US",
        )
        from pathlib import Path as _P
        storage_path = _P(self.settings.scraper_storage_state_path)
        if storage_path.exists():
            ctx_kwargs["storage_state"] = str(storage_path)
        self._ctx = await self._browser.new_context(**ctx_kwargs)
        self._storage_path = storage_path
        self._ctx.set_default_navigation_timeout(45_000)
        self._page = await self._ctx.new_page()
        await self._ensure_authenticated()
        return self

    async def __aexit__(self, *exc: Any) -> None:
        try:
            # Snapshot storage state so any refreshed session cookies survive.
            if self._ctx and getattr(self, "_storage_path", None):
                try:
                    await self._ctx.storage_state(path=str(self._storage_path))
                except Exception:
                    pass
            if self._ctx:
                await self._ctx.close()
            if getattr(self, "_browser", None):
                await self._browser.close()
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
            # Veracross login has reCAPTCHA on the submit button. Automating a
            # re-login just accumulates failed-attempt signals and makes future
            # challenges harder. Bail out cleanly and let the UI show a
            # "re-auth needed" banner that runs `scripts/manual_login.py`.
            raise RuntimeError(
                "needs_reauth: no valid Veracross session — "
                "run `uv run python backend/scripts/manual_login.py` "
                "and sign in manually (reCAPTCHA requires a human)."
            )

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

    def enrollment_grade_detail_url(self, child_vc_id: str, class_id: str) -> str:
        """Parent-portal iframe page listing all grading periods for a class.
        We parse the grading_period hrefs out of this page to discover the
        correct period IDs (they differ by tier: MS uses 13, JS uses 25/27/31/33)."""
        return (
            f"https://portals-embed.veracross.eu/vasantvalleyschool/parent/"
            f"children/{child_vc_id}/classes/{class_id}/grade_detail"
        )


@asynccontextmanager
async def scraper_session():
    client = ScraperClient()
    async with client:
        yield client
