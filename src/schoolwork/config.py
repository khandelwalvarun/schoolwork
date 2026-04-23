from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    veracross_portal_url: str
    veracross_username: str
    veracross_password: str

    scraper_min_delay_sec: float = Field(default=3.0, ge=0.5)
    scraper_max_delay_sec: float = Field(default=6.0, ge=0.5)
    scraper_user_agent: str = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )

    recon_max_pages: int = 250
    recon_max_depth: int = 6


def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
