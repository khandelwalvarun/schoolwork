"""In-app remote-CAPTCHA login to Veracross.

Holds a single Playwright session (at a time) in memory. Streams screenshots
to the frontend over HTTP polling, forwards mouse/keyboard events, and on
success writes `data/storage_state.json` so subsequent headless syncs
reuse the session.

This exists so the parent can solve Veracross's reCAPTCHA from ANY machine
on the LAN (phone, other laptop) — the browser runs on the server, the
interaction happens in the web app.

Not concurrency-safe — one login at a time. Good enough for single-parent use.
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from playwright.async_api import Browser, BrowserContext, Page, Playwright, async_playwright

from ..config import get_settings

log = logging.getLogger(__name__)

VIEWPORT = (1280, 900)  # width, height — also the coord space for click events


@dataclass
class _Session:
    id: str
    pw: Playwright
    browser: Browser
    context: BrowserContext
    page: Page
    started_at: float
    last_png: bytes | None = None
    last_shot_at: float = 0.0
    status: str = "starting"     # "starting" | "ready" | "success" | "error" | "closed"
    message: str = ""
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)


_SESSION: _Session | None = None
_SESSION_LOCK = asyncio.Lock()


async def _cleanup(sess: _Session | None) -> None:
    if sess is None:
        return
    try:
        await sess.context.close()
    except Exception:
        pass
    try:
        await sess.browser.close()
    except Exception:
        pass
    try:
        await sess.pw.stop()
    except Exception:
        pass


async def start_session() -> dict[str, Any]:
    """Launch a fresh Playwright session pointed at the Veracross login page.
    If a session is already open, close it first and start over."""
    global _SESSION
    async with _SESSION_LOCK:
        if _SESSION is not None:
            try:
                await _cleanup(_SESSION)
            except Exception:
                pass
            _SESSION = None

        pw = await async_playwright().start()
        # Headless works — we stream screenshots to the parent's browser.
        # This way the server doesn't need a display.
        browser = await pw.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled"],
        )
        s = get_settings()
        context = await browser.new_context(
            user_agent=s.scraper_user_agent,
            viewport={"width": VIEWPORT[0], "height": VIEWPORT[1]},
            locale="en-US",
        )
        # Load existing storage_state if present (so we resume where we left off)
        storage_path = Path(s.scraper_storage_state_path)
        # Playwright's storage_state is passed at context creation; since we
        # already have a fresh context, import cookies manually if available.
        if storage_path.exists():
            try:
                import json as _json
                state = _json.loads(storage_path.read_text(encoding="utf-8"))
                if state.get("cookies"):
                    await context.add_cookies(state["cookies"])
            except Exception as e:
                log.warning("couldn't preload cookies: %s", e)

        page = await context.new_page()
        from ..services.veracross_creds import current_credentials
        portal = current_credentials()["portal_url"]

        sess = _Session(
            id=f"sess-{int(time.time())}",
            pw=pw, browser=browser, context=context, page=page,
            started_at=time.time(),
        )
        _SESSION = sess
        try:
            await page.goto(portal, wait_until="domcontentloaded", timeout=45_000)
            sess.status = "ready"
            sess.message = f"Loaded {portal}"
        except Exception as e:
            sess.status = "error"
            sess.message = f"Initial load failed: {e}"
            log.warning("remote-login initial goto failed: %s", e)
        await _snapshot(sess)
        return _status_dict(sess)


async def _snapshot(sess: _Session) -> None:
    try:
        png = await sess.page.screenshot(type="png", full_page=False)
        sess.last_png = png
        sess.last_shot_at = time.time()
    except Exception as e:
        log.debug("screenshot failed: %s", e)


async def current_status() -> dict[str, Any]:
    sess = _SESSION
    if sess is None:
        return {"status": "closed"}
    # Refresh snapshot lazily on status poll (cheap, ~50 KB png)
    try:
        await _snapshot(sess)
    except Exception:
        pass
    return _status_dict(sess)


def _status_dict(sess: _Session) -> dict[str, Any]:
    return {
        "id": sess.id,
        "status": sess.status,
        "message": sess.message,
        "url": sess.page.url if not sess.page.is_closed() else None,
        "viewport": {"width": VIEWPORT[0], "height": VIEWPORT[1]},
        "shot_at": sess.last_shot_at,
    }


async def screenshot_png() -> bytes | None:
    """Return the latest PNG. Takes a fresh one if stale (>300ms)."""
    sess = _SESSION
    if sess is None:
        return None
    if time.time() - sess.last_shot_at > 0.3:
        await _snapshot(sess)
    return sess.last_png


async def click(x: int, y: int, button: str = "left") -> dict[str, Any]:
    sess = _SESSION
    if sess is None:
        return {"ok": False, "error": "no session"}
    async with sess.lock:
        try:
            await sess.page.mouse.click(x, y, button=button)
            await asyncio.sleep(0.15)
            await _snapshot(sess)
        except Exception as e:
            return {"ok": False, "error": str(e)}
    return {"ok": True}


async def type_text(text: str) -> dict[str, Any]:
    sess = _SESSION
    if sess is None:
        return {"ok": False, "error": "no session"}
    async with sess.lock:
        try:
            await sess.page.keyboard.type(text, delay=20)
            await _snapshot(sess)
        except Exception as e:
            return {"ok": False, "error": str(e)}
    return {"ok": True}


async def press_key(key: str) -> dict[str, Any]:
    sess = _SESSION
    if sess is None:
        return {"ok": False, "error": "no session"}
    async with sess.lock:
        try:
            await sess.page.keyboard.press(key)
            await asyncio.sleep(0.15)
            await _snapshot(sess)
        except Exception as e:
            return {"ok": False, "error": str(e)}
    return {"ok": True}


async def fill_credentials() -> dict[str, Any]:
    """Auto-fill username + password into the visible inputs — saves the
    parent from typing on a remote screen. CAPTCHA still needs human solve."""
    sess = _SESSION
    if sess is None:
        return {"ok": False, "error": "no session"}
    from ..services.veracross_creds import current_credentials
    c = current_credentials()
    async with sess.lock:
        try:
            ul = sess.page.locator(
                "input[type=email], input[name*='user' i], input[name*='email' i], "
                "input[id*='user' i], input[id*='email' i]"
            ).first
            pl = sess.page.locator("input[type=password]").first
            if await ul.count() > 0:
                await ul.fill(c.get("username") or "")
            if await pl.count() > 0:
                await pl.fill(c.get("password") or "")
            await _snapshot(sess)
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "error": str(e)}


async def check_success() -> dict[str, Any]:
    """Return {logged_in: bool}. Same heuristic as manual_login.py:
    no visible password input AND URL is not /portals/login*."""
    sess = _SESSION
    if sess is None:
        return {"ok": False, "error": "no session"}
    try:
        pwd_visible = await sess.page.locator("input[type=password]").first.is_visible(timeout=300)
    except Exception:
        pwd_visible = False
    on_login = "/portals/login" in (sess.page.url or "")
    logged_in = (not pwd_visible) and (not on_login)
    return {"logged_in": logged_in, "url": sess.page.url}


async def finish_and_save() -> dict[str, Any]:
    """Persist storage_state.json so the headless scraper reuses the session.
    Keeps the browser open so the caller can verify before closing."""
    sess = _SESSION
    if sess is None:
        return {"ok": False, "error": "no session"}
    s = get_settings()
    storage_path = Path(s.scraper_storage_state_path)
    storage_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        await sess.context.storage_state(path=str(storage_path))
        sess.status = "success"
        sess.message = f"Saved {storage_path.stat().st_size} bytes"
        return {"ok": True, "bytes": storage_path.stat().st_size}
    except Exception as e:
        return {"ok": False, "error": str(e)}


async def close_session() -> dict[str, Any]:
    global _SESSION
    async with _SESSION_LOCK:
        sess = _SESSION
        _SESSION = None
    if sess is None:
        return {"ok": True, "already_closed": True}
    await _cleanup(sess)
    return {"ok": True}
