"""Fetch an embed grade_detail page for one (student, class) and inspect its structure."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from playwright.async_api import async_playwright

try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
except Exception:
    pass

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from schoolwork.config import get_settings  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
USER_DATA_DIR = ROOT / "recon" / "user-data"
OUT = ROOT / "recon" / "output" / "embed"
OUT.mkdir(parents=True, exist_ok=True)


async def main() -> None:
    settings = get_settings()
    # Tejas 103460 × class 138358 (one of his classes from the original crawl)
    targets = [
        (103460, 138358, "tejas_138358"),
        (103460, 138359, "tejas_138359"),
        (103609, 138392, "samarth_138392"),  # guess a class id; we'll fix via planner later
    ]

    async with async_playwright() as pw:
        ctx = await pw.chromium.launch_persistent_context(
            user_data_dir=str(USER_DATA_DIR),
            headless=True,
            user_agent=settings.scraper_user_agent,
            viewport={"width": 1440, "height": 900},
            locale="en-US",
        )
        page = ctx.pages[0] if ctx.pages else await ctx.new_page()

        # Ensure authenticated
        await page.goto(settings.veracross_portal_url.rstrip("/"), wait_until="domcontentloaded", timeout=45_000)
        try:
            await page.wait_for_load_state("networkidle", timeout=10_000)
        except Exception:
            pass
        try:
            if await page.locator("input[type=password]").first.is_visible(timeout=1500):
                await page.locator(
                    "input[type=email], input[name*='user' i], input[id*='user' i]"
                ).first.fill(settings.veracross_username)
                await page.locator("input[type=password]").first.fill(settings.veracross_password)
                await page.locator("input[type=password]").first.press("Enter")
                await page.wait_for_load_state("networkidle", timeout=30_000)
        except Exception:
            pass

        for sid, cid, tag in targets:
            url = f"https://portals-embed.veracross.eu/vasantvalleyschool/parent/children/{sid}/classes/{cid}/grade_detail"
            print(f"[*] fetch {tag} -> {url}")
            await page.goto(url, wait_until="networkidle", timeout=45_000)
            html = await page.content()
            (OUT / f"grade_detail_{tag}.html").write_text(html, encoding="utf-8")
            title = await page.title()
            print(f"    title: {title!r}  html: {len(html)} bytes")
            await asyncio.sleep(3.0)

        await ctx.close()


if __name__ == "__main__":
    asyncio.run(main())
