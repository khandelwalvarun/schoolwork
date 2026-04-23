"""Ollama local backend — calls the Ollama HTTP API (no auth, no billing).

Default base URL: http://localhost:11434
Ollama API reference: https://github.com/ollama/ollama/blob/main/docs/api.md

Uses the /api/chat endpoint (supports system+user messages) when a system
prompt is given; falls back to /api/generate for plain prompts.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx

from .base import BackendResponse, LLMBackend

log = logging.getLogger(__name__)

_DEFAULT_BASE = "http://localhost:11434"
_DEFAULT_MODEL = "llama3.2"


class OllamaBackend(LLMBackend):
    def __init__(
        self,
        base_url: str = _DEFAULT_BASE,
        default_model: str = _DEFAULT_MODEL,
        timeout_sec: float = 300.0,
    ) -> None:
        self._base = base_url.rstrip("/")
        self._default_model = default_model
        self._timeout = timeout_sec

    def enabled(self) -> bool:
        return True  # Always "enabled" — will fail at call time if Ollama isn't running.

    async def _check_model_available(self, client: httpx.AsyncClient, model: str) -> bool:
        try:
            r = await client.get(f"{self._base}/api/tags", timeout=5.0)
            if r.status_code == 200:
                names = [m["name"].split(":")[0] for m in r.json().get("models", [])]
                base_name = model.split(":")[0]
                return base_name in names
        except Exception:
            pass
        return False

    async def complete(
        self,
        *,
        system: str | None,
        prompt: str,
        model: str | None,
        max_tokens: int,
    ) -> BackendResponse:
        mdl = model or self._default_model

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            # Check availability early for a clear error message.
            try:
                await client.get(f"{self._base}/api/tags", timeout=3.0)
            except Exception as e:
                raise RuntimeError(
                    f"Ollama not reachable at {self._base}. "
                    f"Start it with `ollama serve`. Error: {e}"
                ) from e

            if system:
                # Use /api/chat with system + user messages.
                payload: dict[str, Any] = {
                    "model": mdl,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": prompt},
                    ],
                    "stream": False,
                    "options": {"num_predict": max_tokens},
                }
                r = await client.post(
                    f"{self._base}/api/chat",
                    json=payload,
                    timeout=self._timeout,
                )
                r.raise_for_status()
                data = r.json()
                text = data["message"]["content"].strip()
                eval_count = data.get("eval_count", 0)
                prompt_eval_count = data.get("prompt_eval_count", 0)
            else:
                # Plain generate.
                payload = {
                    "model": mdl,
                    "prompt": prompt,
                    "stream": False,
                    "options": {"num_predict": max_tokens},
                }
                r = await client.post(
                    f"{self._base}/api/generate",
                    json=payload,
                    timeout=self._timeout,
                )
                r.raise_for_status()
                data = r.json()
                text = data["response"].strip()
                eval_count = data.get("eval_count", 0)
                prompt_eval_count = data.get("prompt_eval_count", 0)

        return BackendResponse(
            text=text,
            model=mdl,
            input_tokens=prompt_eval_count or int(len(prompt.split()) * 1.3),
            output_tokens=eval_count or int(len(text.split()) * 1.3),
        )
