"""One-time manual Veracross login.

Opens a visible Chromium window. You sign in (handle the reCAPTCHA). Script
serialises the authenticated state (cookies + localStorage) to
`recon/storage_state.json` — which the scraper reads on every run.

Run me whenever /api/sync reports "needs_reauth" (session expired).

Usage:
    uv run python backend/scripts/manual_login.py
"""
from __future__ import annotations

import asyncio
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from backend.app.config import get_settings
from playwright.async_api import async_playwright


async def activate_window() -> None:
    """macOS: bring Chrome for Testing to the foreground."""
    try:
        subprocess.run(
            ["osascript", "-e",
             'tell application "Google Chrome for Testing" to activate'],
            timeout=3, check=False,
        )
    except Exception:
        pass


async def main() -> None:
    s = get_settings()
    storage_path = Path(s.scraper_storage_state_path)
    storage_path.parent.mkdir(parents=True, exist_ok=True)
    print(f"portal:  {s.veracross_portal_url}")
    print(f"state:   {storage_path}")
    print()
    print("A Chromium window will open. Sign in (password + CAPTCHA).")
    print("Once you're on the logged-in portal page, this script auto-saves")
    print("the session and closes.")
    print()

    async with async_playwright() as pw:
        ctx = await pw.chromium.launch_persistent_context(
            user_data_dir=s.scraper_user_data_dir,
            headless=False,
            user_agent=s.scraper_user_agent,
            viewport={"width": 1280, "height": 900},
            locale="en-US",
            args=[
                "--disable-blink-features=AutomationControlled",
                "--window-position=0,0",
                "--window-size=1280,900",
                "--new-window",
            ],
        )
        page = ctx.pages[0] if ctx.pages else await ctx.new_page()
        await page.goto(s.veracross_portal_url, wait_until="domcontentloaded", timeout=60_000)

        # Force foreground several times in case the window opens behind others
        for _ in range(3):
            await activate_window()
            try:
                await page.bring_to_front()
            except Exception:
                pass
            await asyncio.sleep(0.3)

        print("=" * 60)
        print("LOOK FOR A BROWSER WINDOW — 'Google Chrome for Testing'")
        print("If you don't see it: ⌘-Tab or check your Dock.")
        print("=" * 60)
        print("waiting for login (poll every 2s, up to 15 minutes)…")
        deadline = 15 * 60
        elapsed = 0
        saved = False
        next_activate = 0
        while elapsed < deadline:
            # Every 5 seconds, re-activate the window so it keeps coming back
            # to the foreground if the user touches another app.
            if elapsed >= next_activate:
                await activate_window()
                try:
                    await page.bring_to_front()
                except Exception:
                    pass
                next_activate = elapsed + 5
            try:
                pwd_visible = await page.locator("input[type=password]").first.is_visible(timeout=500)
            except Exception:
                pwd_visible = False
            on_login = "/portals/login" in page.url
            if not pwd_visible and not on_login:
                print(f"login detected — url={page.url}")
                try:
                    await page.wait_for_load_state("networkidle", timeout=10_000)
                except Exception:
                    pass
                await ctx.storage_state(path=str(storage_path))
                size = storage_path.stat().st_size
                print(f"saved {size} bytes → {storage_path}")
                saved = True
                break
            await asyncio.sleep(2)
            elapsed += 2
        if not saved:
            print("timed out — run me again when ready.")
        try:
            await ctx.close()
        except Exception:
            pass


if __name__ == "__main__":
    asyncio.run(main())
