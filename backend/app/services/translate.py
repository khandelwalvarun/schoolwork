"""LLM-backed title/notes translation — used for Hindi/Sanskrit titles
scraped from Veracross assignment detail pages."""

from __future__ import annotations

import logging
from pathlib import Path

from ..config import get_settings
from ..llm.client import LLMClient

log = logging.getLogger(__name__)

_PROMPT_DIR = Path(__file__).resolve().parent.parent / "llm" / "prompts"


def needs_translation(text: str | None) -> bool:
    """Detect if text contains Devanagari / other non-Latin characters worth translating."""
    if not text:
        return False
    for ch in text:
        o = ord(ch)
        # Devanagari
        if 0x0900 <= o <= 0x097F:
            return True
        # Other Indic scripts / CJK / Arabic
        if 0x0980 <= o <= 0x0DFF or 0x4E00 <= o <= 0x9FFF or 0x0600 <= o <= 0x06FF:
            return True
    return False


async def translate_to_english(text: str | None) -> str | None:
    """Translate `text` to English via the configured LLM. Returns None on
    failure or if no LLM is configured — caller should fall back to original."""
    if not text or not needs_translation(text):
        return text if text else None
    client = LLMClient()
    if not client.enabled():
        return None
    try:
        system = (_PROMPT_DIR / "translate_title.md").read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
    try:
        s = get_settings()
        resp = await client.complete(
            purpose="translate_title",
            model=s.claude_cli_model or None,
            system=system,
            prompt=text,
            max_tokens=200,
            extra_cache_key=text[:80],
        )
        out = (resp.text or "").strip().replace("\n", " ")
        return out or None
    except Exception as e:
        log.warning("translation failed for %r: %s", text[:40], e)
        return None
