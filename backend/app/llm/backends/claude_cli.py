"""Claude Code CLI backend — no API billing; uses Max subscription.

Pipes the full prompt via stdin to avoid Windows 32 KB argv limit.
Falls back to a synchronous subprocess wrapped in asyncio.to_thread
because asyncio.create_subprocess_exec is unreliable on Windows with
large stdin payloads.
"""

from __future__ import annotations

import asyncio
import glob
import logging
import os
import shutil
import subprocess
from pathlib import Path

from .base import BackendResponse, LLMBackend

log = logging.getLogger(__name__)


def _find_claude_exe(explicit_path: str = "") -> str | None:
    if explicit_path and Path(explicit_path).exists():
        return explicit_path
    which = shutil.which("claude")
    if which:
        return which
    home = Path.home()
    patterns = [
        home / "AppData" / "Roaming" / "Claude" / "claude-code" / "*" / "claude.exe",
        Path(os.environ.get("APPDATA", "")) / "Claude" / "claude-code" / "*" / "claude.exe",
    ]
    hits: list[str] = []
    for p in patterns:
        hits.extend(glob.glob(str(p)))
    hits.sort(reverse=True)
    return hits[0] if hits else None


class ClaudeCLIBackend(LLMBackend):
    def __init__(self, cli_path: str = "", timeout_sec: int = 120) -> None:
        self._cli_path = _find_claude_exe(cli_path)
        self._timeout = timeout_sec

    def enabled(self) -> bool:
        return self._cli_path is not None

    async def complete(
        self,
        *,
        system: str | None,
        prompt: str,
        model: str | None,
        max_tokens: int,
    ) -> BackendResponse:
        if self._cli_path is None:
            raise RuntimeError(
                "claude CLI not found. Install Claude Code or set CLAUDE_CLI_PATH in .env."
            )

        full_prompt = (
            prompt if not system else f"{system}\n\n---\n\n{prompt}"
        )
        full_prompt = full_prompt.replace("\x00", "")  # null bytes crash subprocess on Windows

        cmd: list[str] = [self._cli_path, "-p"]
        if model:
            cmd.extend(["--model", model])

        env = os.environ.copy()
        # Windows: claude CLI requires a git-bash reference.
        if os.name == "nt" and not env.get("CLAUDE_CODE_GIT_BASH_PATH"):
            for candidate in (
                r"C:\Program Files\Git\bin\bash.exe",
                r"C:\Program Files\Git\usr\bin\bash.exe",
                r"D:\Program Files\Git\usr\bin\bash.exe",
                r"D:\Program Files\Git\bin\bash.exe",
            ):
                if Path(candidate).exists():
                    env["CLAUDE_CODE_GIT_BASH_PATH"] = candidate
                    break

        payload = full_prompt.encode("utf-8")

        def _run() -> tuple[int, bytes, bytes]:
            res = subprocess.run(
                cmd,
                input=payload,
                capture_output=True,
                timeout=self._timeout,
                env=env,
            )
            return res.returncode, res.stdout, res.stderr

        try:
            rc, stdout_b, stderr_b = await asyncio.to_thread(_run)
        except subprocess.TimeoutExpired as e:
            raise RuntimeError(f"claude CLI timed out after {self._timeout}s") from e
        except Exception as e:
            raise RuntimeError(f"claude CLI process error: {e}") from e

        if rc != 0:
            err = stderr_b.decode("utf-8", errors="replace")[:500]
            raise RuntimeError(f"claude CLI exited {rc}: {err}")

        text = stdout_b.decode("utf-8", errors="replace").strip()
        in_t = int(len(full_prompt.split()) * 1.3)
        out_t = int(len(text.split()) * 1.3)
        return BackendResponse(
            text=text,
            model=model or "claude-cli-default",
            input_tokens=in_t,
            output_tokens=out_t,
        )
