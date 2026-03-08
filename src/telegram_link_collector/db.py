"""SQLite persistence for Telegram messages, links, and images."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path


@dataclass
class PendingMessage:
    row_id: int
    chat_id: int
    telegram_message_id: int
    text: str
    caption: str
    raw_json: dict


class Database:
    def __init__(self, db_path: str) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
        self._init_schema()

    def close(self) -> None:
        self.conn.close()

    def _init_schema(self) -> None:
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS state (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER NOT NULL,
                telegram_message_id INTEGER NOT NULL,
                message_date_utc TEXT,
                text TEXT NOT NULL DEFAULT '',
                caption TEXT NOT NULL DEFAULT '',
                raw_json TEXT NOT NULL,
                processed_at_utc TEXT,
                created_at_utc TEXT NOT NULL,
                UNIQUE(chat_id, telegram_message_id)
            );

            CREATE TABLE IF NOT EXISTS links (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                url TEXT NOT NULL UNIQUE,
                source_chat_id INTEGER,
                source_telegram_message_id INTEGER,
                note TEXT,
                first_seen_at_utc TEXT NOT NULL,
                karakeep_synced_at_utc TEXT,
                karakeep_status TEXT
            );

            CREATE TABLE IF NOT EXISTS images (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER NOT NULL,
                telegram_message_id INTEGER NOT NULL,
                file_id TEXT NOT NULL,
                file_unique_id TEXT NOT NULL UNIQUE,
                width INTEGER,
                height INTEGER,
                file_size INTEGER,
                local_path TEXT,
                created_at_utc TEXT NOT NULL
            );
            """
        )
        self.conn.commit()

    @staticmethod
    def _now() -> str:
        return datetime.now(UTC).isoformat()

    def get_state(self, key: str) -> str | None:
        row = self.conn.execute("SELECT value FROM state WHERE key = ?", (key,)).fetchone()
        return None if row is None else str(row["value"])

    def set_state(self, key: str, value: str) -> None:
        self.conn.execute(
            "INSERT INTO state(key, value) VALUES(?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )
        self.conn.commit()

    def upsert_message(self, *, chat_id: int, telegram_message_id: int, message_date_utc: str | None, text: str, caption: str, raw: dict) -> bool:
        cur = self.conn.execute(
            """
            INSERT OR IGNORE INTO messages(
                chat_id, telegram_message_id, message_date_utc, text, caption, raw_json, created_at_utc
            ) VALUES(?, ?, ?, ?, ?, ?, ?)
            """,
            (chat_id, telegram_message_id, message_date_utc, text, caption, json.dumps(raw, ensure_ascii=True), self._now()),
        )
        self.conn.commit()
        return cur.rowcount > 0

    def add_image(
        self,
        *,
        chat_id: int,
        telegram_message_id: int,
        file_id: str,
        file_unique_id: str,
        width: int | None,
        height: int | None,
        file_size: int | None,
        local_path: str | None,
    ) -> bool:
        cur = self.conn.execute(
            """
            INSERT OR IGNORE INTO images(
                chat_id, telegram_message_id, file_id, file_unique_id, width, height, file_size, local_path, created_at_utc
            ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (chat_id, telegram_message_id, file_id, file_unique_id, width, height, file_size, local_path, self._now()),
        )
        self.conn.commit()
        return cur.rowcount > 0

    def pending_messages(self, *, limit: int = 1000) -> list[PendingMessage]:
        rows = self.conn.execute(
            """
            SELECT id, chat_id, telegram_message_id, text, caption, raw_json
            FROM messages
            WHERE processed_at_utc IS NULL
            ORDER BY id ASC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        results: list[PendingMessage] = []
        for row in rows:
            results.append(
                PendingMessage(
                    row_id=int(row["id"]),
                    chat_id=int(row["chat_id"]),
                    telegram_message_id=int(row["telegram_message_id"]),
                    text=str(row["text"]),
                    caption=str(row["caption"]),
                    raw_json=json.loads(str(row["raw_json"])),
                )
            )
        return results

    def mark_processed(self, row_ids: list[int]) -> None:
        if not row_ids:
            return
        marks = ",".join("?" for _ in row_ids)
        query = f"UPDATE messages SET processed_at_utc = ? WHERE id IN ({marks})"
        self.conn.execute(query, (self._now(), *row_ids))
        self.conn.commit()

    def add_link(self, *, url: str, source_chat_id: int, source_telegram_message_id: int, note: str | None) -> bool:
        cur = self.conn.execute(
            """
            INSERT OR IGNORE INTO links(
                url, source_chat_id, source_telegram_message_id, note, first_seen_at_utc
            ) VALUES(?, ?, ?, ?, ?)
            """,
            (url, source_chat_id, source_telegram_message_id, note, self._now()),
        )
        self.conn.commit()
        return cur.rowcount > 0

    def max_telegram_message_id(self, *, chat_id: int) -> int | None:
        row = self.conn.execute(
            "SELECT MAX(telegram_message_id) AS max_id FROM messages WHERE chat_id = ?",
            (chat_id,),
        ).fetchone()
        if row is None:
            return None
        value = row["max_id"]
        if value is None:
            return None
        return int(value)

    def unsynced_links(self, *, limit: int = 200) -> list[sqlite3.Row]:
        return self.conn.execute(
            """
            SELECT id, url, note
            FROM links
            WHERE karakeep_synced_at_utc IS NULL
            ORDER BY id ASC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

    def mark_link_synced(self, *, link_id: int, status: str) -> None:
        self.conn.execute(
            "UPDATE links SET karakeep_synced_at_utc = ?, karakeep_status = ? WHERE id = ?",
            (self._now(), status, link_id),
        )
        self.conn.commit()
