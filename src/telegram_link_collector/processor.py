"""Message processing: extract and normalize URLs, then store deduplicated links."""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urlsplit, urlunsplit

from telegram_link_collector.db import Database

_URL_RE = re.compile(r"https?://[^\s<>()\[\]{}\"']+", re.IGNORECASE)


@dataclass
class ProcessStats:
    processed_messages: int = 0
    discovered_links: int = 0
    inserted_links: int = 0


def _normalize_url(raw_url: str) -> str | None:
    trimmed = raw_url.strip().rstrip(".,;:!?)")
    if not trimmed:
        return None

    parts = urlsplit(trimmed)
    if parts.scheme not in {"http", "https"}:
        return None
    if not parts.netloc:
        return None

    # Canonicalize host case and remove fragments for stable de-duplication.
    host = parts.netloc.lower()
    normalized = urlunsplit((parts.scheme.lower(), host, parts.path, parts.query, ""))
    return normalized


def _extract_urls_from_text(raw_text: str) -> set[str]:
    urls: set[str] = set()
    for match in _URL_RE.findall(raw_text):
        normalized = _normalize_url(match)
        if normalized:
            urls.add(normalized)
    return urls


def _extract_text_link_entities(message_raw: dict) -> set[str]:
    urls: set[str] = set()
    for key in ("entities", "caption_entities"):
        for entity in message_raw.get(key, []):
            url = entity.get("url")
            if isinstance(url, str):
                normalized = _normalize_url(url)
                if normalized:
                    urls.add(normalized)
    return urls


def process_pending_messages(db: Database, *, batch_size: int = 1000) -> ProcessStats:
    pending = db.pending_messages(limit=batch_size)
    stats = ProcessStats()

    for message in pending:
        stats.processed_messages += 1

        urls = set()
        urls |= _extract_urls_from_text(message.text)
        urls |= _extract_urls_from_text(message.caption)
        urls |= _extract_text_link_entities(message.raw_json)
        stats.discovered_links += len(urls)

        for url in urls:
            inserted = db.add_link(
                url=url,
                source_chat_id=message.chat_id,
                source_telegram_message_id=message.telegram_message_id,
                note=f"Telegram chat {message.chat_id}, message {message.telegram_message_id}",
            )
            if inserted:
                stats.inserted_links += 1

    db.mark_processed([item.row_id for item in pending])
    return stats

