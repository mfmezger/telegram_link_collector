"""Pydantic settings for telegram_link_collector."""

from __future__ import annotations

from functools import lru_cache

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    telegram_bot_token: str
    telegram_allowed_chat_id: int
    sqlite_path: str = "/data/collector.db"
    media_dir: str = "/data/media"
    telegram_poll_timeout_seconds: int = 30
    telegram_download_images: bool = True
    service_daily_hour: int = 3
    service_daily_minute: int = 0
    service_idle_sleep_seconds: int = 2
    telegram_hybrid_backfill_enabled: bool = False
    telegram_api_id: int | None = None
    telegram_api_hash: str | None = None
    telegram_backfill_session_path: str = "/data/telethon.session"
    telegram_backfill_chat_ref: str | None = None
    telegram_backfill_limit: int = 0
    karakeep_url: str | None = None
    karakeep_api_key: str | None = None
    karakeep_sync_enabled: bool = False

    @model_validator(mode="after")
    def _validate_conditional_requirements(self) -> "Settings":
        if self.karakeep_sync_enabled and (not self.karakeep_url or not self.karakeep_api_key):
            raise ValueError("KARAKEEP_SYNC_ENABLED=true requires KARAKEEP_URL and KARAKEEP_API_KEY")
        if self.telegram_hybrid_backfill_enabled and (self.telegram_api_id is None or not self.telegram_api_hash):
            raise ValueError("TELEGRAM_HYBRID_BACKFILL_ENABLED=true requires TELEGRAM_API_ID and TELEGRAM_API_HASH")
        return self


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
