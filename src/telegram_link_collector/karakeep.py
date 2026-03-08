"""Optional KaraKeep synchronization for collected links."""

from __future__ import annotations

from dataclasses import dataclass

import httpx

from telegram_link_collector.db import Database


@dataclass
class KaraKeepSyncStats:
    attempted: int = 0
    synced: int = 0
    failed: int = 0


class KaraKeepClient:
    def __init__(self, *, base_url: str, api_key: str, timeout_seconds: int = 30) -> None:
        self.base_url = base_url.rstrip("/")
        self.client = httpx.Client(
            timeout=timeout_seconds,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
        )

    def close(self) -> None:
        self.client.close()

    def upload_link(self, *, url: str, note: str | None = None) -> tuple[bool, str]:
        payload = {"type": "link", "url": url}
        if note:
            payload["note"] = note

        response = self.client.post(f"{self.base_url}/api/v1/bookmarks", json=payload)
        if response.status_code in {200, 201}:
            return True, f"ok:{response.status_code}"

        detail = response.text.strip()
        if len(detail) > 300:
            detail = detail[:300]
        return False, f"http:{response.status_code}:{detail}"


def sync_unsynced_links(db: Database, karakeep: KaraKeepClient, *, batch_size: int = 200) -> KaraKeepSyncStats:
    stats = KaraKeepSyncStats()
    rows = db.unsynced_links(limit=batch_size)

    for row in rows:
        if row.id is None:
            continue
        stats.attempted += 1
        ok, status = karakeep.upload_link(url=row.url, note=row.note)
        if ok:
            db.mark_link_synced(link_id=row.id, status=status)
            stats.synced += 1
        else:
            stats.failed += 1

    return stats
