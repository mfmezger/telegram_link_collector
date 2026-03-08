"""CLI entrypoint for telegram_link_collector."""

from __future__ import annotations

import argparse

from telegram_link_collector.config import Settings
from telegram_link_collector.db import Database
from telegram_link_collector.karakeep import KaraKeepClient, sync_unsynced_links
from telegram_link_collector.backfill import run_backfill
from telegram_link_collector.service import poll_once, run_daily_processing, run_service
from telegram_link_collector.telegram_api import TelegramBotClient


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Collect Telegram links and images from one allowed chat")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("run-service", help="Long-running mode: poll + daily processing")
    subparsers.add_parser("poll-once", help="Fetch Telegram updates once and persist messages")
    subparsers.add_parser("process-now", help="Process pending messages now and optionally sync KaraKeep")
    subparsers.add_parser("sync-karakeep", help="Sync unsynced links to KaraKeep now")
    subparsers.add_parser("backfill-now", help="Run Telethon history backfill now (hybrid mode)")

    return parser


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    settings = Settings.from_env()

    if args.command == "run-service":
        run_service(settings)
        return

    if args.command == "poll-once":
        db = Database(settings.sqlite_path)
        telegram = TelegramBotClient(settings.telegram_bot_token)
        try:
            updates, stored = poll_once(db, telegram, settings)
            print("poll-once", f"updates={updates}", f"stored_messages={stored}")
        finally:
            telegram.close()
            db.close()
        return

    if args.command == "process-now":
        db = Database(settings.sqlite_path)
        try:
            run_daily_processing(db, settings)
        finally:
            db.close()
        return

    if args.command == "sync-karakeep":
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
        return

    if args.command == "backfill-now":
        if not settings.telegram_hybrid_backfill_enabled:
            raise ValueError("Hybrid backfill disabled. Set TELEGRAM_HYBRID_BACKFILL_ENABLED=true")
        db = Database(settings.sqlite_path)
        try:
            stats = run_backfill(db, settings)
            print("backfill", f"scanned={stats.scanned}", f"new_messages={stats.inserted_messages}", f"new_images={stats.inserted_images}")
        finally:
            db.close()
        return

    parser.print_help()
