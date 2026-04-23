"""One-off probe to fetch the portals-embed subdomain for one student, save the HTML,
and inspect its structure. Helps us understand where the real assignment data lives.
"""

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
    targets = [
        (
            103460,
            "tejas",
            "https://portals-embed.veracross.eu/vasantvalleyschool/parent/planner?p=103460&school_year=2026",
        ),
        (
            103609,
            "samarth",
            "https://portals-embed.veracross.eu/vasantvalleyschool/parent/planner?p=103609&school_year=2026",
        ),
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

        # Re-login against main portal if session expired.
        try:
            await page.goto(settings.veracross_portal_url.rstrip("/"), wait_until="domcontentloaded", timeout=45_000)
            await page.wait_for_load_state("networkidle", timeout=10_000)
        except Exception:
            pass
        try:
            if await page.locator("input[type=password]").first.is_visible(timeout=2000):
                print("re-logging in…")
                await page.locator(
                    "input[type=email], input[name*='user' i], input[id*='user' i]"
                ).first.fill(settings.veracross_username)
                await page.locator("input[type=password]").first.fill(settings.veracross_password)
                await page.locator("input[type=password]").first.press("Enter")
                await page.wait_for_load_state("networkidle", timeout=30_000)
        except Exception:
            pass

        for vc_id, name, url in targets:
            print(f"[*] fetching planner for {name} ({vc_id})")
            await page.goto(url, wait_until="networkidle", timeout=45_000)
            html = await page.content()
            (OUT / f"planner_{name}_{vc_id}.html").write_text(html, encoding="utf-8")
            await page.screenshot(path=str(OUT / f"planner_{name}_{vc_id}.png"), full_page=True)
            title = await page.title()
            print(f"    title: {title!r}  html: {len(html)} bytes")

            # Also try upcoming-assignments direct embed URL
            for variant in [
                f"https://portals-embed.veracross.eu/vasantvalleyschool/parent/student/{vc_id}/upcoming-assignments",
                f"https://portals-embed.veracross.eu/vasantvalleyschool/parent/student/{vc_id}/overview",
                f"https://portals-embed.veracross.eu/vasantvalleyschool/parent/student/{vc_id}/recent-updates",
            ]:
                tag = variant.rsplit("/", 1)[-1]
                try:
                    await page.goto(variant, wait_until="networkidle", timeout=45_000)
                    html = await page.content()
                    (OUT / f"{tag}_{name}.html").write_text(html, encoding="utf-8")
                    print(f"    {tag}: {len(html)} bytes")
                except Exception as e:
                    print(f"    {tag}: error {e}")
                await asyncio.sleep(3.0)

        await ctx.close()


if __name__ == "__main__":
    asyncio.run(main())
