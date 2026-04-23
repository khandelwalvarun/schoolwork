"""Pluggable LLM client.

Supported backends (set LLM_BACKEND in .env):
  "claude"  — Claude Code CLI subprocess (Max subscription, no API billing)
  "ollama"  — Local Ollama server (http://localhost:11434 by default)
  "openai"  — OpenAI-compatible HTTP API (GPT-4o, Codex, LM Studio, vLLM…)

Per-purpose overrides are supported via LLM_PURPOSE_BACKENDS (JSON map).
Example .env additions:

    LLM_BACKEND=claude
    OLLAMA_MODEL=llama3.2
    LLM_PURPOSE_BACKENDS={"ask": "ollama", "digest_preamble": "claude"}

Every call is logged to the `llm_calls` table (cost_inr=None for CLI/local).
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone

from ..config import get_settings
from ..db import get_async_session
from ..models import LLMCall
from .backends.base import LLMBackend
from .backends.claude_cli import ClaudeCLIBackend
from .backends.ollama import OllamaBackend
from .backends.openai_compat import OpenAICompatBackend

log = logging.getLogger(__name__)


@dataclass
class LLMResponse:
    text: str
    input_tokens: int
    output_tokens: int
    cost_inr: float | None
    model: str          # "backend/model-name" e.g. "claude/claude-haiku-4-5"


def _build_backend(name: str) -> LLMBackend:
    s = get_settings()
    if name == "ollama":
        return OllamaBackend(
            base_url=s.ollama_base_url,
            default_model=s.ollama_model,
            timeout_sec=s.ollama_timeout_sec,
        )
    if name == "openai":
        return OpenAICompatBackend(
            base_url=s.llm_openai_base_url,
            api_key=s.openai_api_key,
            default_model=s.openai_model,
            timeout_sec=s.openai_timeout_sec,
        )
    # Default: "claude" (Max subscription, no API billing)
    return ClaudeCLIBackend(
        cli_path=s.claude_cli_path,
        timeout_sec=s.claude_cli_timeout_sec,
    )


def _parse_purpose_map() -> dict[str, str]:
    s = get_settings()
    raw = (s.llm_purpose_backends or "").strip()
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except Exception:
        log.warning("LLM_PURPOSE_BACKENDS is not valid JSON — ignoring: %s", raw)
        return {}


class LLMClient:
    """Thin router: picks the right backend per-purpose, calls it, logs result."""

    def __init__(self) -> None:
        self._settings = get_settings()
        self._purpose_map: dict[str, str] = _parse_purpose_map()
        self._primary: LLMBackend = _build_backend(self._settings.llm_backend)

    def enabled(self) -> bool:
        return self._primary.enabled()

    def _backend_for(self, purpose: str) -> tuple[str, LLMBackend]:
        """Return (backend_name, backend_instance) for this call purpose."""
        name = self._purpose_map.get(purpose, self._settings.llm_backend)
        if name == self._settings.llm_backend:
            return name, self._primary
        # Different backend than primary — build a fresh one each time
        # (backends are cheap to construct; no persistent connections to reuse).
        return name, _build_backend(name)

    def _resolve_model(self, backend_name: str, model: str | None) -> str | None:
        """Fill in per-backend default model when caller didn't specify one."""
        if model:
            return model
        s = self._settings
        if backend_name == "claude":
            return s.claude_cli_model or None
        if backend_name == "ollama":
            return s.ollama_model or None
        if backend_name == "openai":
            return s.openai_model or None
        return None

    async def complete(
        self,
        *,
        purpose: str,
        model: str | None = None,
        system: str | None = None,
        prompt: str,
        max_tokens: int = 1024,
        extra_cache_key: str = "",
    ) -> LLMResponse:
        backend_name, backend = self._backend_for(purpose)
        effective_model = self._resolve_model(backend_name, model)

        input_hash = hashlib.sha1(
            f"{backend_name}|{effective_model or ''}|{system or ''}|{prompt}|{extra_cache_key}".encode()
        ).hexdigest()

        try:
            resp = await backend.complete(
                system=system,
                prompt=prompt,
                model=effective_model,
                max_tokens=max_tokens,
            )
        except Exception as e:
            label = f"{backend_name}/{effective_model or 'default'}"
            await self._log(purpose, label, 0, 0, input_hash, False, repr(e)[:500])
            raise

        label = f"{backend_name}/{resp.model}"
        await self._log(purpose, label, resp.input_tokens, resp.output_tokens, input_hash, True, None)

        return LLMResponse(
            text=resp.text,
            input_tokens=resp.input_tokens,
            output_tokens=resp.output_tokens,
            cost_inr=None,
            model=label,
        )

    async def _log(
        self,
        purpose: str,
        model: str,
        in_t: int,
        out_t: int,
        input_hash: str,
        success: bool,
        error: str | None,
    ) -> None:
        try:
            async with get_async_session() as session:
                session.add(
                    LLMCall(
                        purpose=purpose,
                        model=model,
                        input_tokens=in_t,
                        output_tokens=out_t,
                        cost_inr=None,
                        input_hash=input_hash,
                        success=1 if success else 0,
                        error=error,
                        created_at=datetime.now(tz=timezone.utc),
                    )
                )
                await session.commit()
        except Exception:
            log.exception("failed to log llm_call (non-fatal)")
