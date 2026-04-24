"""Veracross credential store — layered on top of the `.env` defaults.

Prefs live at `data/veracross_creds.json` (gitignored). On GET, we redact the
password. On PUT, we persist + invalidate the config cache so the next
scraper run picks up the new values without a restart.

Precedence (high → low):
    1. data/veracross_creds.json
    2. .env / process environment
    3. hard-coded defaults in config.py
"""
from __future__ import annotations

import json
import tempfile
import threading
from pathlib import Path
from typing import Any

from ..config import get_settings

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
_CREDS_PATH = _REPO_ROOT / "data" / "veracross_creds.json"
_LOCK = threading.Lock()


def _read_file() -> dict[str, Any]:
    if not _CREDS_PATH.exists():
        return {}
    try:
        return json.loads(_CREDS_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _write_file(data: dict[str, Any]) -> None:
    with _LOCK:
        _CREDS_PATH.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            "w", delete=False, dir=_CREDS_PATH.parent, encoding="utf-8"
        ) as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
            tmp = f.name
        Path(tmp).replace(_CREDS_PATH)
        try:
            _CREDS_PATH.chmod(0o600)  # limit to user on disk
        except Exception:
            pass


def current_credentials() -> dict[str, str]:
    """Merge file override with env-backed config. Returns all fields."""
    s = get_settings()
    base = {
        "portal_url": s.veracross_portal_url,
        "username": s.veracross_username,
        "password": s.veracross_password,
    }
    overlay = _read_file()
    return {**base, **{k: v for k, v in overlay.items() if v}}


def public_view() -> dict[str, Any]:
    """Same as current_credentials() but with the password redacted.
    Includes a flag saying whether any override is currently in effect."""
    merged = current_credentials()
    file_override = _read_file()
    has_pw = bool(merged.get("password"))
    return {
        "portal_url": merged.get("portal_url"),
        "username": merged.get("username"),
        "has_password": has_pw,
        "password_length": len(merged.get("password") or ""),
        "override_active": bool(file_override),
        "override_fields": sorted([k for k, v in file_override.items() if v]),
    }


def save_credentials(patch: dict[str, Any]) -> dict[str, Any]:
    """Merge patch into the override file. Any field absent from the patch
    is untouched. To clear an override, pass an empty string for that field."""
    current = _read_file()
    for k in ("portal_url", "username", "password"):
        if k in patch:
            v = patch[k]
            if v is None or v == "":
                current.pop(k, None)
            else:
                current[k] = str(v)
    _write_file(current)
    return public_view()
