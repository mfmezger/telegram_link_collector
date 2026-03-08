"""Hybrid backfill from Telegram history via Telethon (MTProto)."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC
from pathlib import Path
from typing import Any

from telegram_link_collector.config import Settings
from telegram_link_collector.db import Database


@dataclass
class BackfillStats:
    scanned: int = 0
    inserted_messages: int = 0
    inserted_images: int = 0


def _matches_allowed_chat(entity_id: int, allowed_chat_id: int) -> bool:
    if allowed_chat_id >= 0:
        return entity_id == allowed_chat_id
    if allowed_chat_id <= -1000000000000:
        return entity_id == abs(allowed_chat_id) - 1000000000000
    return entity_id == abs(allowed_chat_id)


async def _resolve_entity(client: Any, settings: Settings) -> Any:
    if settings.telegram_backfill_chat_ref:
        return await client.get_entity(settings.telegram_backfill_chat_ref)

    try:
        return await client.get_entity(settings.telegram_allowed_chat_id)
    except Exception:
        pass

    dialogs = await client.get_dialogs(limit=200)
    for dialog in dialogs:
        entity = dialog.entity
        entity_id = int(getattr(entity, "id", 0) or 0)
        if _matches_allowed_chat(entity_id, settings.telegram_allowed_chat_id):
            return entity

    raise RuntimeError(
        "Could not resolve backfill chat entity. Set TELEGRAM_BACKFILL_CHAT_REF "
        "(username/invite/chat id) explicitly."
    )


async def _run_backfill_async(db: Database, settings: Settings) -> BackfillStats:
    from telethon import TelegramClient

    if settings.telegram_api_id is None or not settings.telegram_api_hash:
        raise ValueError("Backfill requires TELEGRAM_API_ID and TELEGRAM_API_HASH")

    session_path = Path(settings.telegram_backfill_session_path)
    session_path.parent.mkdir(parents=True, exist_ok=True)

    stats = BackfillStats()
    min_message_id = db.max_telegram_message_id(chat_id=settings.telegram_allowed_chat_id) or 0
    iter_limit = None if settings.telegram_backfill_limit <= 0 else settings.telegram_backfill_limit

    async with TelegramClient(str(session_path), settings.telegram_api_id, settings.telegram_api_hash) as client:
        await client.start(bot_token=settings.telegram_bot_token)
        entity = await _resolve_entity(client, settings)

        async for message in client.iter_messages(entity, min_id=min_message_id, reverse=True, limit=iter_limit):
            msg_id = getattr(message, "id", None)
            if not isinstance(msg_id, int):
                continue

            stats.scanned += 1
            msg_text = message.message or ""
            raw = message.to_dict() if hasattr(message, "to_dict") else {"id": msg_id, "message": msg_text}
            msg_date = message.date
            msg_date_iso = None
            if msg_date is not None:
                msg_date_iso = msg_date.astimezone(UTC).isoformat()

            inserted = db.upsert_message(
                chat_id=settings.telegram_allowed_chat_id,
                telegram_message_id=msg_id,
                message_date_utc=msg_date_iso,
                text=msg_text,
                caption="",
                raw=raw,
            )
            if inserted:
                stats.inserted_messages += 1

            photo = getattr(message, "photo", None)
            if photo is None:
                continue

            file_unique_id = f"telethon-photo-{photo.id}"
            local_path: str | None = None
            if settings.telegram_download_images:
                destination = Path(settings.media_dir) / f"{file_unique_id}.jpg"
                if not destination.exists():
                    await client.download_media(message, file=str(destination))
                local_path = str(destination)

            added = db.add_image(
                chat_id=settings.telegram_allowed_chat_id,
                telegram_message_id=msg_id,
                file_id=file_unique_id,
                file_unique_id=file_unique_id,
                width=getattr(photo, "w", None),
                height=getattr(photo, "h", None),
                file_size=None,
                local_path=local_path,
            )
            if added:
                stats.inserted_images += 1

    return stats


def run_backfill(db: Database, settings: Settings) -> BackfillStats:
    return asyncio.run(_run_backfill_async(db, settings))
