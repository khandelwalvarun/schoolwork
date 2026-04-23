"""OpenAI-compatible backend — works with:
  • OpenAI API (GPT-4o, o1, etc.)
  • OpenAI Codex / codex-mini (same API, different base URL if self-hosted)
  • Any OpenAI-compatible endpoint (LM Studio, vLLM, LocalAI, etc.)

Set LLM_OPENAI_BASE_URL to override the endpoint (default: https://api.openai.com/v1).
OPENAI_API_KEY must be set for api.openai.com; leave blank for un-authed local servers.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from .base import BackendResponse, LLMBackend

log = logging.getLogger(__name__)

_DEFAULT_BASE = "https://api.openai.com/v1"
_DEFAULT_MODEL = "gpt-4o-mini"


class OpenAICompatBackend(LLMBackend):
    def __init__(
        self,
        base_url: str = _DEFAULT_BASE,
        api_key: str = "",
        default_model: str = _DEFAULT_MODEL,
        timeout_sec: float = 120.0,
    ) -> None:
        self._base = base_url.rstrip("/")
        self._api_key = api_key
        self._default_model = default_model
        self._timeout = timeout_sec

    def enabled(self) -> bool:
        # Enabled if we have an API key, OR if pointing at a local server (localhost / 127.)
        if self._api_key:
            return True
        local_hints = ("localhost", "127.", "0.0.0.0", "::1")
        return any(h in self._base for h in local_hints)

    async def complete(
        self,
        *,
        system: str | None,
        prompt: str,
        model: str | None,
        max_tokens: int,
    ) -> BackendResponse:
        mdl = model or self._default_model
        headers: dict[str, str] = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"

        messages: list[dict[str, str]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        payload: dict[str, Any] = {
            "model": mdl,
            "messages": messages,
            "max_tokens": max_tokens,
        }

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            r = await client.post(
                f"{self._base}/chat/completions",
                headers=headers,
                json=payload,
            )
            try:
                r.raise_for_status()
            except httpx.HTTPStatusError as e:
                body = r.text[:400]
                raise RuntimeError(f"OpenAI API error {r.status_code}: {body}") from e

        data = r.json()
        text = data["choices"][0]["message"]["content"].strip()
        usage = data.get("usage", {})
        return BackendResponse(
            text=text,
            model=mdl,
            input_tokens=usage.get("prompt_tokens", int(len(prompt.split()) * 1.3)),
            output_tokens=usage.get("completion_tokens", int(len(text.split()) * 1.3)),
        )
