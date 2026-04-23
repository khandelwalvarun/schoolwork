"""Quick test of the LLM backend routing.

Usage:
    uv run python backend/scripts/test_llm.py
    uv run python backend/scripts/test_llm.py --backend ollama --model llama3.2
    uv run python backend/scripts/test_llm.py --backend openai --model gpt-4o-mini
    uv run python backend/scripts/test_llm.py --purpose ask   # uses purpose-map override
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
except Exception:
    pass


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--backend", choices=["claude", "ollama", "openai"], default=None)
    parser.add_argument("--model", default=None)
    parser.add_argument("--purpose", default="test")
    parser.add_argument("--prompt", default="Say 'hello from {backend}' in exactly 5 words.")
    args = parser.parse_args()

    # If --backend is given, temporarily override the env.
    if args.backend:
        import os
        os.environ["LLM_BACKEND"] = args.backend

    # Re-import after possible env override.
    from backend.app.llm.client import LLMClient  # noqa: PLC0415

    client = LLMClient()
    actual_backend = args.backend or client._settings.llm_backend
    print(f"[test_llm] backend={actual_backend}  purpose={args.purpose}  model={args.model or 'default'}")
    print(f"[test_llm] prompt: {args.prompt}")

    resp = await client.complete(
        purpose=args.purpose,
        model=args.model,
        prompt=args.prompt,
        max_tokens=100,
    )
    print(f"\n[test_llm] model used : {resp.model}")
    print(f"[test_llm] in/out tokens: {resp.input_tokens}/{resp.output_tokens}")
    print(f"\n--- response ---\n{resp.text}\n---")


if __name__ == "__main__":
    asyncio.run(main())
