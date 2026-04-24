"""Lightweight live auth probe for the Veracross portal.

Loads cookies from the persisted storage_state.json, does ONE unauthenticated-looking
GET to the portal with those cookies set, and decides whether the session
is currently valid.

Heuristic:
  - storage_state.json missing → "never"
  - GET final URL contains "/portals/login" → "expired"
  - GET 2xx with a portal-looking body (has `Portals.schoolYear` or the
    user's name, or didn't redirect to login) → "valid"
  - Non-2xx network issue → "unknown" (don't trash the state unnecessarily)

Much cheaper than spinning up Playwright — just httpx with the cookies.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx

from ..config import get_settings
from .veracross_creds import current_credentials


def _load_cookies(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data.get("cookies", []) or []
    except Exception:
        return []


async def probe() -> dict[str, Any]:
    """Return {
      state: 'valid' | 'expired' | 'never' | 'unknown',
      checked_at: iso timestamp,
      detail: str,
      storage_state_bytes: int | None,
      cookie_count: int,
      final_url: str | None,
    }"""
    s = get_settings()
    storage_path = Path(s.scraper_storage_state_path)
    checked_at = datetime.now(tz=timezone.utc).isoformat()
    if not storage_path.exists():
        return {
            "state": "never",
            "checked_at": checked_at,
            "detail": "No storage_state.json on disk yet.",
            "storage_state_bytes": None,
            "cookie_count": 0,
            "final_url": None,
        }
    cookies = _load_cookies(storage_path)
    if not cookies:
        return {
            "state": "never",
            "checked_at": checked_at,
            "detail": "storage_state.json has no cookies.",
            "storage_state_bytes": storage_path.stat().st_size,
            "cookie_count": 0,
            "final_url": None,
        }

    # Build httpx cookies — domain-scoped
    jar = httpx.Cookies()
    for c in cookies:
        try:
            jar.set(
                name=c["name"],
                value=c["value"],
                domain=c.get("domain", "").lstrip("."),
                path=c.get("path", "/"),
            )
        except Exception:
            continue

    creds = current_credentials()
    portal_url = creds.get("portal_url") or s.veracross_portal_url
    headers = {
        "User-Agent": s.scraper_user_agent,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }
    try:
        async with httpx.AsyncClient(
            follow_redirects=True, timeout=15.0, cookies=jar, headers=headers,
        ) as client:
            r = await client.get(portal_url)
    except httpx.HTTPError as e:
        return {
            "state": "unknown",
            "checked_at": checked_at,
            "detail": f"network error: {type(e).__name__}: {e}",
            "storage_state_bytes": storage_path.stat().st_size,
            "cookie_count": len(cookies),
            "final_url": None,
        }

    final_url = str(r.url)
    body = r.text or ""
    low = body.lower()
    # Primary signal: Veracross redirects unauthenticated requests to
    # /portals/login. Not being redirected + 2xx is strong evidence of a
    # live session.
    on_login_page = "/portals/login" in final_url
    has_login_form = (
        'name="username"' in body
        and 'name="password"' in body
        and 'name="authenticity_token"' in body
    )
    auth_markers = (
        "Portals.currentUser"  in body
        or "MyChildrenParent"  in body
        or 'class="vx-nav' in body
        or "Parent Portal" in body and "Messages" in body and "Calendar" in body
    )
    if on_login_page or has_login_form:
        state = "expired"
        detail = "Portal redirected to the login page."
    elif r.status_code >= 400:
        state = "unknown"
        detail = f"HTTP {r.status_code} from portal."
    elif auth_markers:
        state = "valid"
        detail = "Portal returned the authenticated home page."
    elif r.status_code == 200:
        # No redirect + no login form + 2xx = almost certainly authenticated.
        # Markup changed → detail says so but we don't panic.
        state = "valid"
        detail = "Portal responded with the home page (no redirect to login)."
    else:
        state = "unknown"
        detail = f"Portal returned {r.status_code}; couldn't confirm."
    return {
        "state": state,
        "checked_at": checked_at,
        "detail": detail,
        "storage_state_bytes": storage_path.stat().st_size,
        "cookie_count": len(cookies),
        "final_url": final_url,
    }
