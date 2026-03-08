"""SQLModel persistence for Telegram messages, links, and images."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import UniqueConstraint, func
from sqlalchemy.exc import IntegrityError
from sqlmodel import Field, Session, SQLModel, create_engine, select


class State(SQLModel, table=True):
    key: str = Field(primary_key=True)
    value: str


class Message(SQLModel, table=True):
    __table_args__ = (UniqueConstraint("chat_id", "telegram_message_id", name="uq_messages_chat_message"),)

    id: int | None = Field(default=None, primary_key=True)
    chat_id: int
    telegram_message_id: int
    message_date_utc: str | None = None
    text: str = ""
    caption: str = ""
    raw_json: str
    processed_at_utc: str | None = None
    created_at_utc: str


class Link(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    url: str = Field(index=True, unique=True)
    source_chat_id: int | None = None
    source_telegram_message_id: int | None = None
    note: str | None = None
    first_seen_at_utc: str
    karakeep_synced_at_utc: str | None = None
    karakeep_status: str | None = None


class Image(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    chat_id: int
    telegram_message_id: int
    file_id: str
    file_unique_id: str = Field(index=True, unique=True)
    width: int | None = None
    height: int | None = None
    file_size: int | None = None
    local_path: str | None = None
    created_at_utc: str


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
        self.engine = create_engine(f"sqlite:///{self.db_path}")
        SQLModel.metadata.create_all(self.engine)

    def close(self) -> None:
        # Engine is managed by SQLAlchemy; explicit close is not required here.
        return None

    @staticmethod
    def _now() -> str:
        return datetime.now(UTC).isoformat()

    def get_state(self, key: str) -> str | None:
        with Session(self.engine) as session:
            item = session.get(State, key)
            return None if item is None else item.value

    def set_state(self, key: str, value: str) -> None:
        with Session(self.engine) as session:
            item = session.get(State, key)
            if item is None:
                session.add(State(key=key, value=value))
            else:
                item.value = value
                session.add(item)
            session.commit()

    def upsert_message(self, *, chat_id: int, telegram_message_id: int, message_date_utc: str | None, text: str, caption: str, raw: dict) -> bool:
        with Session(self.engine) as session:
            existing = session.exec(
                select(Message).where(Message.chat_id == chat_id, Message.telegram_message_id == telegram_message_id)
            ).first()
            if existing is not None:
                return False

            item = Message(
                chat_id=chat_id,
                telegram_message_id=telegram_message_id,
                message_date_utc=message_date_utc,
                text=text,
                caption=caption,
                raw_json=json.dumps(raw, ensure_ascii=True),
                created_at_utc=self._now(),
            )
            session.add(item)
            session.commit()
            return True

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
        with Session(self.engine) as session:
            existing = session.exec(select(Image).where(Image.file_unique_id == file_unique_id)).first()
            if existing is not None:
                return False

            item = Image(
                chat_id=chat_id,
                telegram_message_id=telegram_message_id,
                file_id=file_id,
                file_unique_id=file_unique_id,
                width=width,
                height=height,
                file_size=file_size,
                local_path=local_path,
                created_at_utc=self._now(),
            )
            session.add(item)
            session.commit()
            return True

    def pending_messages(self, *, limit: int = 1000) -> list[PendingMessage]:
        with Session(self.engine) as session:
            rows = session.exec(
                select(Message)
                .where(Message.processed_at_utc.is_(None))
                .order_by(Message.id)
                .limit(limit)
            ).all()

        results: list[PendingMessage] = []
        for row in rows:
            if row.id is None:
                continue
            results.append(
                PendingMessage(
                    row_id=row.id,
                    chat_id=row.chat_id,
                    telegram_message_id=row.telegram_message_id,
                    text=row.text,
                    caption=row.caption,
                    raw_json=json.loads(row.raw_json),
                )
            )
        return results

    def mark_processed(self, row_ids: list[int]) -> None:
        if not row_ids:
            return
        with Session(self.engine) as session:
            rows = session.exec(select(Message).where(Message.id.in_(row_ids))).all()
            now = self._now()
            for row in rows:
                row.processed_at_utc = now
                session.add(row)
            session.commit()

    def add_link(self, *, url: str, source_chat_id: int, source_telegram_message_id: int, note: str | None) -> bool:
        with Session(self.engine) as session:
            existing = session.exec(select(Link).where(Link.url == url)).first()
            if existing is not None:
                return False

            item = Link(
                url=url,
                source_chat_id=source_chat_id,
                source_telegram_message_id=source_telegram_message_id,
                note=note,
                first_seen_at_utc=self._now(),
            )
            session.add(item)
            try:
                session.commit()
                return True
            except IntegrityError:
                session.rollback()
                return False

    def max_telegram_message_id(self, *, chat_id: int) -> int | None:
        with Session(self.engine) as session:
            value = session.exec(
                select(func.max(Message.telegram_message_id)).where(Message.chat_id == chat_id)
            ).one()
        if value is None:
            return None
        return int(value)

    def unsynced_links(self, *, limit: int = 200) -> list[Link]:
        with Session(self.engine) as session:
            return session.exec(
                select(Link)
                .where(Link.karakeep_synced_at_utc.is_(None))
                .order_by(Link.id)
                .limit(limit)
            ).all()

    def mark_link_synced(self, *, link_id: int, status: str) -> None:
        with Session(self.engine) as session:
            item = session.get(Link, link_id)
            if item is None:
                return
            item.karakeep_synced_at_utc = self._now()
            item.karakeep_status = status
            session.add(item)
            session.commit()

