"""Central settings. All values loaded from .env (or environment). Safe defaults where possible."""

from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
DATA_ROOT = REPO_ROOT / "data"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(REPO_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Where ALL persistent state lives (SQLite DB, attachments, spellbee lists,
    # storage_state.json, ui_prefs, syllabus seeds, etc.). Override with DATA_DIR
    # in .env to put the data somewhere other than the repo-relative default.
    data_dir: str = str(DATA_ROOT)

    # Database — defaults point inside data_dir. Env overrides still win.
    database_url: str = f"sqlite+aiosqlite:///{DATA_ROOT / 'app.db'}"
    sync_database_url: str = f"sqlite:///{DATA_ROOT / 'app.db'}"

    # Timezone
    tz: str = "Asia/Kolkata"

    # Veracross
    veracross_portal_url: str = "https://portals.veracross.eu/vasantvalleyschool/parent"
    veracross_username: str = ""
    veracross_password: str = ""

    # Mindspark — narrow metrics-only scrape, slow rate.
    # See migration 0020 for the scope contract (no question content;
    # just per-session aggregates and per-topic progress snapshots).
    mindspark_enabled: bool = False
    mindspark_login_url: str = "https://learn.mindspark.in/Student/onboard/login/en"
    # Credentials are per-kid since each kid has their own Mindspark
    # account. Set MINDSPARK_USERNAME_<child_id>=… and
    # MINDSPARK_PASSWORD_<child_id>=… in .env. The
    # `mindspark_credentials_for(child_id)` helper resolves them.
    # Slow-rate guards. Don't reduce these without re-confirming the
    # ToS-risk conversation with the user.
    mindspark_min_delay_sec: float = Field(default=15.0, ge=5.0)
    mindspark_max_delay_sec: float = Field(default=30.0, ge=10.0)
    mindspark_storage_state_dir: str = str(DATA_ROOT / "mindspark_state")
    # Stealth posture: visible browser by default. Override with
    # MINDSPARK_HEADLESS=true if running on a server without a display
    # (the scraper still applies playwright-stealth + the other 6 fixes).
    mindspark_headless: bool = False

    # Scraper pacing
    scraper_min_delay_sec: float = Field(default=3.0, ge=0.5)
    scraper_max_delay_sec: float = Field(default=6.0, ge=0.5)
    scraper_user_agent: str = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
    scraper_user_data_dir: str = str(REPO_ROOT / "recon" / "user-data")
    scraper_storage_state_path: str = str(DATA_ROOT / "storage_state.json")

    # Grades — period IDs for this school year (Veracross internal). Comma-separated.
    # 2026-27 Vasant Valley: 13=LC1, 15=LC2, 19=LC3, 21=LC4.
    grading_period_ids: str = "13,15,19,21"
    grading_period_current: int = 21

    # ── LLM backends ──────────────────────────────────────────────────────────
    # Primary backend to use for all LLM calls unless overridden per-purpose.
    # Choices: "claude" | "ollama" | "openai"
    llm_backend: str = "claude"

    # Claude Code CLI (Max subscription — no per-token billing)
    # Path resolution: explicit CLAUDE_CLI_PATH wins; else search PATH; else
    # fall back to %APPDATA%\Claude\claude-code\*\claude.exe.
    claude_cli_path: str = ""
    claude_cli_model: str = ""  # e.g. "claude-haiku-4-5"; empty = CLI default
    claude_cli_timeout_sec: int = 120

    # Override the model used by services/practice_session.py — the
    # iterative practice-prep generator. Defaults to claude-opus-4-5
    # because Opus's reasoning + curriculum grounding is the right tier
    # for student-facing test material. Override per-deployment if Opus
    # quota is tight.
    practice_llm_model: str = "claude-opus-4-5"

    # Ollama (local, no billing)
    # Set OLLAMA_BASE_URL / OLLAMA_MODEL in .env if non-default.
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.2"          # default model; override per-call via model=
    ollama_timeout_sec: int = 300

    # OpenAI-compatible endpoint (GPT-4o, Codex, LM Studio, vLLM, …)
    # For the real OpenAI API set OPENAI_API_KEY.
    # For a local server (LM Studio on :1234, etc.) leave the key blank and
    # set LLM_OPENAI_BASE_URL to your server's URL.
    openai_api_key: str = ""
    llm_openai_base_url: str = "https://api.openai.com/v1"
    openai_model: str = "gpt-4o-mini"
    openai_timeout_sec: int = 120

    # Per-purpose backend overrides — JSON map, e.g.:
    #   LLM_PURPOSE_BACKENDS={"ask":"ollama","digest_preamble":"claude"}
    # Any purpose not listed falls back to llm_backend.
    llm_purpose_backends: str = "{}"

    # Telegram
    telegram_bot_token: str = ""
    telegram_chat_ids: str = ""  # comma-separated

    # SMTP
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = "cockpit@localhost"
    email_to: str = ""  # comma-separated

    # MCP
    mcp_bearer_token: str = ""
    mcp_public_url: str = "http://localhost:7777"

    # App
    app_secret: str = "change-me-please"
    app_host: str = "0.0.0.0"
    app_port: int = 7777
    log_level: str = "INFO"


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()  # type: ignore[call-arg]
    return _settings


def mindspark_credentials_for(child_id: int) -> tuple[str, str] | None:
    """Resolve Mindspark credentials for a given child id.

    Reads MINDSPARK_USERNAME_<id> + MINDSPARK_PASSWORD_<id> from env
    (works around Pydantic's struggle with dynamic key sets). Returns
    None when either is missing — caller should skip that kid.
    """
    import os
    u = os.environ.get(f"MINDSPARK_USERNAME_{child_id}", "").strip()
    p = os.environ.get(f"MINDSPARK_PASSWORD_{child_id}", "").strip()
    if not u or not p:
        return None
    return (u, p)
