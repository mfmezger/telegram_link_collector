"""Thin Telegram Bot API client."""

from __future__ import annotations

from pathlib import Path

import httpx


class TelegramBotClient:
    def __init__(self, token: str, *, timeout_seconds: int = 60) -> None:
        self.token = token
        self.base_url = f"https://api.telegram.org/bot{token}"
        self.file_base_url = f"https://api.telegram.org/file/bot{token}"
        self.client = httpx.Client(timeout=timeout_seconds)

    def close(self) -> None:
        self.client.close()

    def get_updates(self, *, offset: int, timeout_seconds: int) -> list[dict]:
        response = self.client.post(
            f"{self.base_url}/getUpdates",
            json={
                "offset": offset,
                "timeout": timeout_seconds,
                "allowed_updates": ["message"],
            },
        )
        response.raise_for_status()
        data = response.json()
        if not data.get("ok"):
            raise RuntimeError(f"Telegram getUpdates failed: {data}")
        return list(data.get("result", []))

    def get_file_path(self, file_id: str) -> str:
        response = self.client.post(f"{self.base_url}/getFile", json={"file_id": file_id})
        response.raise_for_status()
        data = response.json()
        if not data.get("ok"):
            raise RuntimeError(f"Telegram getFile failed: {data}")
        file_path = data.get("result", {}).get("file_path")
        if not file_path:
            raise RuntimeError(f"Telegram getFile returned no file_path for file_id={file_id}")
        return str(file_path)

    def download_file(self, *, file_path: str, destination: Path) -> None:
        destination.parent.mkdir(parents=True, exist_ok=True)
        with self.client.stream("GET", f"{self.file_base_url}/{file_path}") as response:
            response.raise_for_status()
            with destination.open("wb") as output:
                for chunk in response.iter_bytes():
                    output.write(chunk)

