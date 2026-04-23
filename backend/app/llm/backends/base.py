"""Abstract base for all LLM backends."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class BackendResponse:
    text: str
    model: str            # resolved model name/tag
    input_tokens: int     # approximate (word-count based for CLI backends)
    output_tokens: int


class LLMBackend(ABC):
    """Every backend must implement this single method."""

    @abstractmethod
    async def complete(
        self,
        *,
        system: str | None,
        prompt: str,
        model: str | None,         # caller-requested model (may be None → backend default)
        max_tokens: int,
    ) -> BackendResponse:
        ...

    def enabled(self) -> bool:
        """Return False if the backend has missing required config/binaries."""
        return True
