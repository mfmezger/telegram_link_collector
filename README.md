# telegram-link-collector

Collect links and images from exactly one Telegram chat, store them in SQLite, and optionally sync links to KaraKeep.

## Features

- Continuous Telegram polling via Bot API.
- Strict allowlist for one chat only: `TELEGRAM_ALLOWED_CHAT_ID`.
- Daily processing pipeline for deduplicated links.
- Optional hybrid backfill via Telethon to recover missed history after downtime.
- Optional KaraKeep sync for collected links.
- Docker Compose deployment with `restart: unless-stopped`.

## Architecture

1. Ingestion (real-time): `getUpdates` polling stores raw Telegram messages.
2. Ingestion (hybrid backfill, optional): daily Telethon history fetch inserts missing messages.
3. Processing (daily): parse pending messages, extract URLs, deduplicate into `links` table.
4. Sync (optional): upload unsynced links to KaraKeep.

## Telegram Setup Guide

### 1. Create a Telegram bot

1. Open Telegram and start chat with `@BotFather`.
2. Run `/newbot`.
3. Set name and username.
4. Copy the bot token and put it in `.env` as `TELEGRAM_BOT_TOKEN`.

### 2. Add bot to your target chat

- Private chat: just message the bot.
- Group/supergroup/channel: add the bot to that chat.

If group privacy mode blocks messages, disable it in BotFather:

1. `/mybots` -> your bot -> `Bot Settings` -> `Group Privacy` -> `Turn off`.

### 3. Get the chat ID

Use one of these methods:

Method A (quick):
1. Send a message in the target chat.
2. Call:

```bash
curl -s "https://api.telegram.org/bot<YOUR_BOT_TOKEN>/getUpdates"
```

3. Find `message.chat.id` in the response.
4. Put it in `.env` as `TELEGRAM_ALLOWED_CHAT_ID`.

Notes:
- Private chat IDs are usually positive.
- Supergroups/channels often look like `-100...`.

Method B (if you prefer app tooling): use any Telegram ID bot and verify the ID matches your target chat.

## Installation and Configuration

### 1. Clone and prepare env

```bash
cp .env.example .env
```

### 2. Required `.env` values

```bash
TELEGRAM_BOT_TOKEN=...
TELEGRAM_ALLOWED_CHAT_ID=123456789
SQLITE_PATH=/data/collector.db
MEDIA_DIR=/data/media
```

### 3. Optional: Hybrid backfill (recommended)

Hybrid mode helps recover messages after long downtime.

1. Create Telegram API credentials at `https://my.telegram.org`:
- `API ID`
- `API Hash`

2. Set in `.env`:

```bash
TELEGRAM_HYBRID_BACKFILL_ENABLED=true
TELEGRAM_API_ID=123456
TELEGRAM_API_HASH=...
# optional, improves entity resolution reliability
TELEGRAM_BACKFILL_CHAT_REF=@your_chat_or_numeric_id
TELEGRAM_BACKFILL_SESSION_PATH=/data/telethon.session
TELEGRAM_BACKFILL_LIMIT=0
```

### 4. Optional: KaraKeep sync

```bash
KARAKEEP_SYNC_ENABLED=true
KARAKEEP_URL=http://your-karakeep-host
KARAKEEP_API_KEY=...
```

## Run with Docker Compose

```bash
docker compose up -d --build
```

This service is configured with:
- Persistent volume `./data:/data`
- `restart: unless-stopped`

Check logs:

```bash
docker compose logs -f telegram-link-collector
```

Stop:

```bash
docker compose down
```

## CLI Commands

- `telegram-link-collector run-service`
  - Long-running mode (poll + daily processing).
- `telegram-link-collector poll-once`
  - One polling cycle.
- `telegram-link-collector process-now`
  - Process pending messages now.
- `telegram-link-collector backfill-now`
  - Run Telethon backfill now (hybrid must be enabled).
- `telegram-link-collector sync-karakeep`
  - Retry KaraKeep sync for unsynced links.

## Scheduling Behavior

- Service checks daily run window with:
  - `SERVICE_DAILY_HOUR`
  - `SERVICE_DAILY_MINUTE`
- It records the last processed date in DB state, so daily run happens once per day.
- On restart, all unprocessed stored messages are still processed.
- With hybrid enabled, missed Telegram history can be backfilled before processing.

## Database Tables

- `messages`: raw Telegram payloads + processing marker.
- `links`: unique URLs + KaraKeep sync status.
- `images`: image metadata and optional local file path.
- `state`: offsets/checkpoints (`telegram_last_update_id`, `daily_last_processed_date`).

## Security Notes

- This collector accepts only one configured Telegram chat ID.
- Messages from all other chats are ignored.
- Keep `.env` secret (bot token, API hash, KaraKeep key).

## Troubleshooting

- `Missing TELEGRAM_BOT_TOKEN`:
  - Set token in `.env`.
- `Missing TELEGRAM_ALLOWED_CHAT_ID`:
  - Get the exact chat ID via `getUpdates` and set it.
- No messages collected in group:
  - Check bot is added and Group Privacy is disabled.
- Hybrid backfill fails to resolve chat:
  - Set `TELEGRAM_BACKFILL_CHAT_REF` explicitly.
- KaraKeep sync fails:
  - Verify `KARAKEEP_URL`, key, and endpoint reachability from container.

## Alignment with zukuagent

`zukuagent` uses allowlisted Telegram chat IDs (`TELEGRAM_ALLOWED_CHAT_IDS`).
This project applies the same access-control concept with one required chat ID (`TELEGRAM_ALLOWED_CHAT_ID`).
