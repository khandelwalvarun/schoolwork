"""LLM-backed title/notes translation — used for Hindi/Sanskrit titles
scraped from Veracross assignment detail pages.

Backed by a content-addressed cache (`translation_cache` table) keyed on
sha256(source_text) + target_lang. Hindi/Sanskrit titles repeat
frequently across days and kids, so the cache eliminates the bulk of
redundant Opus calls.
"""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime
from pathlib import Path

from sqlalchemy import select, update

from ..config import get_settings
from ..db import get_async_session
from ..llm.client import LLMClient
from ..models.translation_cache import TranslationCache

log = logging.getLogger(__name__)

_PROMPT_DIR = Path(__file__).resolve().parent.parent / "llm" / "prompts"

# We only translate to English today, but encode the lang as a column so
# adding (e.g.) Hindi → simplified-English-for-young-readers later is a
# row-level config change, not a schema change.
TARGET_LANG_EN = "en"


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


def _normalise(text: str) -> str:
    """Normalise whitespace before hashing — "पाठ ५  " and "पाठ ५" should
    not be two distinct cache entries."""
    return " ".join(text.split())


def _hash(text: str) -> str:
    return hashlib.sha256(_normalise(text).encode("utf-8")).hexdigest()


async def _cache_lookup(text: str, target: str) -> str | None:
    """Check the cache. Bumps hits/last_used_at on hit."""
    sha = _hash(text)
    try:
        async with get_async_session() as session:
            row = (
                await session.execute(
                    select(TranslationCache).where(
                        TranslationCache.text_sha256 == sha,
                        TranslationCache.target_lang == target,
                    )
                )
            ).scalar_one_or_none()
            if row is None:
                return None
            translated = row.translated_text
            await session.execute(
                update(TranslationCache)
                .where(TranslationCache.id == row.id)
                .values(hits=row.hits + 1, last_used_at=datetime.utcnow())
            )
            await session.commit()
            return translated
    except Exception as e:
        log.warning("translation cache lookup failed: %s", e)
        return None


async def _cache_store(text: str, target: str, translated: str, model: str | None) -> None:
    sha = _hash(text)
    try:
        async with get_async_session() as session:
            # Re-check: another concurrent caller may have just inserted
            # the same key. Treat duplicate-insert as a hit on the
            # existing row.
            existing = (
                await session.execute(
                    select(TranslationCache).where(
                        TranslationCache.text_sha256 == sha,
                        TranslationCache.target_lang == target,
                    )
                )
            ).scalar_one_or_none()
            if existing is not None:
                return
            row = TranslationCache(
                text_sha256=sha,
                target_lang=target,
                source_text=_normalise(text),
                translated_text=translated,
                model=model,
            )
            session.add(row)
            await session.commit()
    except Exception as e:
        log.warning("translation cache store failed: %s", e)


async def translate_to_english(text: str | None) -> str | None:
    """Translate `text` to English via the configured LLM. Returns None on
    failure or if no LLM is configured — caller should fall back to original.

    Uses a sha256-keyed cache to avoid repeat Opus calls on identical
    titles/notes (Hindi/Sanskrit titles like "पाठ ५ का अभ्यास" recur
    across days and kids).
    """
    if not text or not needs_translation(text):
        return text if text else None

    # Cache hit?
    cached = await _cache_lookup(text, TARGET_LANG_EN)
    if cached is not None:
        return cached

    client = LLMClient()
    if not client.enabled():
        return None
    try:
        system = (_PROMPT_DIR / "translate_title.md").read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
    s = get_settings()
    model = s.claude_cli_model or None
    try:
        resp = await client.complete(
            purpose="translate_title",
            model=model,
            system=system,
            prompt=text,
            max_tokens=200,
            extra_cache_key=text[:80],
        )
        out = (resp.text or "").strip().replace("\n", " ")
        if not out:
            return None
        # Persist for next time.
        await _cache_store(text, TARGET_LANG_EN, out, model)
        return out
    except Exception as e:
        log.warning("translation failed for %r: %s", text[:40], e)
        return None
