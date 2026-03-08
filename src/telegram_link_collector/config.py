"""Environment-backed settings for telegram_link_collector."""

from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv


def _parse_bool(value: str | bool | None, *, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass
class Settings:
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

    @classmethod
    def from_env(cls) -> "Settings":
        load_dotenv()

        token = os.getenv("TELEGRAM_BOT_TOKEN")
        if not token:
            raise ValueError("Missing TELEGRAM_BOT_TOKEN")

        allowed_chat_raw = os.getenv("TELEGRAM_ALLOWED_CHAT_ID")
        if not allowed_chat_raw:
            raise ValueError("Missing TELEGRAM_ALLOWED_CHAT_ID")

        karakeep_url = os.getenv("KARAKEEP_URL")
        karakeep_api_key = os.getenv("KARAKEEP_API_KEY")

        sync_enabled = _parse_bool(os.getenv("KARAKEEP_SYNC_ENABLED"), default=False)
        if sync_enabled and (not karakeep_url or not karakeep_api_key):
            raise ValueError("KARAKEEP_SYNC_ENABLED=true requires KARAKEEP_URL and KARAKEEP_API_KEY")

        backfill_enabled = _parse_bool(os.getenv("TELEGRAM_HYBRID_BACKFILL_ENABLED"), default=False)
        api_id_raw = os.getenv("TELEGRAM_API_ID")
        api_hash = os.getenv("TELEGRAM_API_HASH")
        if backfill_enabled and (not api_id_raw or not api_hash):
            raise ValueError("TELEGRAM_HYBRID_BACKFILL_ENABLED=true requires TELEGRAM_API_ID and TELEGRAM_API_HASH")

        return cls(
            telegram_bot_token=token,
            telegram_allowed_chat_id=int(allowed_chat_raw),
            sqlite_path=os.getenv("SQLITE_PATH", "/data/collector.db"),
            media_dir=os.getenv("MEDIA_DIR", "/data/media"),
            telegram_poll_timeout_seconds=int(os.getenv("TELEGRAM_POLL_TIMEOUT_SECONDS", "30")),
            telegram_download_images=_parse_bool(os.getenv("TELEGRAM_DOWNLOAD_IMAGES"), default=True),
            service_daily_hour=int(os.getenv("SERVICE_DAILY_HOUR", "3")),
            service_daily_minute=int(os.getenv("SERVICE_DAILY_MINUTE", "0")),
            service_idle_sleep_seconds=int(os.getenv("SERVICE_IDLE_SLEEP_SECONDS", "2")),
            telegram_hybrid_backfill_enabled=backfill_enabled,
            telegram_api_id=None if api_id_raw is None else int(api_id_raw),
            telegram_api_hash=api_hash,
            telegram_backfill_session_path=os.getenv("TELEGRAM_BACKFILL_SESSION_PATH", "/data/telethon.session"),
            telegram_backfill_chat_ref=os.getenv("TELEGRAM_BACKFILL_CHAT_REF"),
            telegram_backfill_limit=int(os.getenv("TELEGRAM_BACKFILL_LIMIT", "0")),
            karakeep_url=karakeep_url,
            karakeep_api_key=karakeep_api_key,
            karakeep_sync_enabled=sync_enabled,
        )
