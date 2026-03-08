"""CLI entrypoint for telegram_link_collector."""

from __future__ import annotations

import typer

from telegram_link_collector.config import Settings, get_settings
from telegram_link_collector.db import Database
from telegram_link_collector.karakeep import KaraKeepClient, sync_unsynced_links
from telegram_link_collector.backfill import run_backfill
from telegram_link_collector.service import poll_once, run_daily_processing, run_service
from telegram_link_collector.telegram_api import TelegramBotClient

app = typer.Typer(help="Collect Telegram links and images from one allowed chat")


def _settings() -> Settings:
    return get_settings()


@app.command("run-service")
def run_service_command() -> None:
    run_service(_settings())


@app.command("poll-once")
def poll_once_command() -> None:
    settings = _settings()
    db = Database(settings.sqlite_path)
    telegram = TelegramBotClient(settings.telegram_bot_token)
    try:
        updates, stored = poll_once(db, telegram, settings)
        print("poll-once", f"updates={updates}", f"stored_messages={stored}")
    finally:
        telegram.close()
        db.close()


@app.command("process-now")
def process_now_command() -> None:
    settings = _settings()
    db = Database(settings.sqlite_path)
    try:
        run_daily_processing(db, settings)
    finally:
        db.close()


@app.command("sync-karakeep")
def sync_karakeep_command() -> None:
    settings = _settings()
    if not settings.karakeep_sync_enabled or not settings.karakeep_url or not settings.karakeep_api_key:
        raise ValueError("KaraKeep sync not configured. Set KARAKEEP_SYNC_ENABLED=true and credentials.")

    db = Database(settings.sqlite_path)
    karakeep = KaraKeepClient(base_url=settings.karakeep_url, api_key=settings.karakeep_api_key)
    try:
        stats = sync_unsynced_links(db, karakeep)
        print("karakeep", f"attempted={stats.attempted}", f"synced={stats.synced}", f"failed={stats.failed}")
    finally:
        karakeep.close()
        db.close()


@app.command("backfill-now")
def backfill_now_command() -> None:
    settings = _settings()
    if not settings.telegram_hybrid_backfill_enabled:
        raise ValueError("Hybrid backfill disabled. Set TELEGRAM_HYBRID_BACKFILL_ENABLED=true")
    db = Database(settings.sqlite_path)
    try:
        stats = run_backfill(db, settings)
        print("backfill", f"scanned={stats.scanned}", f"new_messages={stats.inserted_messages}", f"new_images={stats.inserted_images}")
    finally:
        db.close()


def main() -> None:
    app()
