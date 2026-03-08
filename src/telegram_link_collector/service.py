"""Service loop: poll Telegram, persist messages/images, and run daily processing."""

from __future__ import annotations

import time
from datetime import datetime
from pathlib import Path

from telegram_link_collector.backfill import run_backfill
from telegram_link_collector.config import Settings
from telegram_link_collector.db import Database
from telegram_link_collector.karakeep import KaraKeepClient, sync_unsynced_links
from telegram_link_collector.processor import process_pending_messages
from telegram_link_collector.telegram_api import TelegramBotClient


def _message_date_iso(message: dict) -> str | None:
    unix_ts = message.get("date")
    if isinstance(unix_ts, int):
        return datetime.fromtimestamp(unix_ts).isoformat()
    return None


def _store_message_and_images(db: Database, telegram: TelegramBotClient, settings: Settings, message: dict) -> bool:
    chat_id = message.get("chat", {}).get("id")
    if chat_id != settings.telegram_allowed_chat_id:
        return False

    telegram_message_id = message.get("message_id")
    if not isinstance(telegram_message_id, int):
        return False

    text = message.get("text") or ""
    caption = message.get("caption") or ""

    inserted_message = db.upsert_message(
        chat_id=chat_id,
        telegram_message_id=telegram_message_id,
        message_date_utc=_message_date_iso(message),
        text=text,
        caption=caption,
        raw=message,
    )

    photos = message.get("photo") or []
    if not photos:
        return inserted_message

    largest = max(photos, key=lambda p: int(p.get("file_size") or 0))
    file_id = largest.get("file_id")
    file_unique_id = largest.get("file_unique_id")
    if not isinstance(file_id, str) or not isinstance(file_unique_id, str):
        return inserted_message

    local_path: str | None = None
    if settings.telegram_download_images:
        tg_file_path = telegram.get_file_path(file_id)
        suffix = Path(tg_file_path).suffix or ".jpg"
        path = Path(settings.media_dir) / f"{file_unique_id}{suffix}"
        if not path.exists():
            telegram.download_file(file_path=tg_file_path, destination=path)
        local_path = str(path)

    db.add_image(
        chat_id=chat_id,
        telegram_message_id=telegram_message_id,
        file_id=file_id,
        file_unique_id=file_unique_id,
        width=largest.get("width"),
        height=largest.get("height"),
        file_size=largest.get("file_size"),
        local_path=local_path,
    )
    return inserted_message


def poll_once(db: Database, telegram: TelegramBotClient, settings: Settings) -> tuple[int, int]:
    stored = 0
    offset = int(db.get_state("telegram_last_update_id") or "0")
    updates = telegram.get_updates(offset=offset + 1, timeout_seconds=settings.telegram_poll_timeout_seconds)
    max_seen = offset

    for update in updates:
        update_id = update.get("update_id")
        if isinstance(update_id, int):
            max_seen = max(max_seen, update_id)

        message = update.get("message")
        if not isinstance(message, dict):
            continue

        if _store_message_and_images(db, telegram, settings, message):
            stored += 1

    if max_seen != offset:
        db.set_state("telegram_last_update_id", str(max_seen))

    return len(updates), stored


def run_daily_processing(db: Database, settings: Settings) -> None:
    if settings.telegram_hybrid_backfill_enabled:
        backfill = run_backfill(db, settings)
        print(
            "backfill",
            f"scanned={backfill.scanned}",
            f"new_messages={backfill.inserted_messages}",
            f"new_images={backfill.inserted_images}",
        )

    processed = process_pending_messages(db)
    print(
        "processed",
        f"messages={processed.processed_messages}",
        f"links_found={processed.discovered_links}",
        f"new_links={processed.inserted_links}",
    )

    if settings.karakeep_sync_enabled and settings.karakeep_url and settings.karakeep_api_key:
        karakeep = KaraKeepClient(base_url=settings.karakeep_url, api_key=settings.karakeep_api_key)
        try:
            stats = sync_unsynced_links(db, karakeep)
            print("karakeep", f"attempted={stats.attempted}", f"synced={stats.synced}", f"failed={stats.failed}")
        finally:
            karakeep.close()


def should_run_daily(now: datetime, *, last_processed_date: str | None, target_hour: int, target_minute: int) -> bool:
    today = now.date().isoformat()
    if last_processed_date == today:
        return False
    return (now.hour, now.minute) >= (target_hour, target_minute)


def run_service(settings: Settings) -> None:
    db = Database(settings.sqlite_path)
    telegram = TelegramBotClient(settings.telegram_bot_token)

    try:
        print("service started", f"allowed_chat_id={settings.telegram_allowed_chat_id}")
        while True:
            updates_total, stored_messages = poll_once(db, telegram, settings)
            if updates_total > 0:
                print("poll", f"updates={updates_total}", f"stored_messages={stored_messages}")

            now = datetime.now()
            last_daily = db.get_state("daily_last_processed_date")
            if should_run_daily(
                now,
                last_processed_date=last_daily,
                target_hour=settings.service_daily_hour,
                target_minute=settings.service_daily_minute,
            ):
                run_daily_processing(db, settings)
                db.set_state("daily_last_processed_date", now.date().isoformat())

            time.sleep(settings.service_idle_sleep_seconds)
    finally:
        telegram.close()
        db.close()
