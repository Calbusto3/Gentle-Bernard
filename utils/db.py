from __future__ import annotations

import asyncio
import aiosqlite
from pathlib import Path
from typing import Optional

_DB_PATH = Path(__file__).resolve().parent.parent / "data" / "bot.db"


async def ensure_db() -> aiosqlite.Connection:
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = await aiosqlite.connect(_DB_PATH.as_posix())
    await conn.execute("PRAGMA journal_mode=WAL;")
    await migrate(conn)
    return conn


async def migrate(conn: aiosqlite.Connection) -> None:
    await conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS schema_version (
            version INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS counters (
            name TEXT PRIMARY KEY,
            value INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS confessions (
            id INTEGER PRIMARY KEY,
            author_id INTEGER NOT NULL,
            guild_id INTEGER NOT NULL,
            channel_id INTEGER NOT NULL,
            message_id INTEGER NOT NULL,
            thread_id INTEGER,
            parent_id INTEGER,
            content TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            deleted INTEGER NOT NULL DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS confession_bans (
            user_id INTEGER PRIMARY KEY,
            guild_id INTEGER NOT NULL,
            reason TEXT,
            moderator_id INTEGER,
            active INTEGER NOT NULL DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        -- Voice temp hubs
        CREATE TABLE IF NOT EXISTS voctemp_hubs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id INTEGER NOT NULL,
            category_id INTEGER NOT NULL,
            hub_channel_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            perms_mask INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        -- Voice temp rooms
        CREATE TABLE IF NOT EXISTS voctemp_rooms (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id INTEGER NOT NULL,
            hub_id INTEGER NOT NULL,
            owner_id INTEGER NOT NULL,
            voice_channel_id INTEGER NOT NULL,
            text_channel_id INTEGER,
            control_message_id INTEGER,
            active INTEGER NOT NULL DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """
    )
    await conn.commit()


async def next_counter(conn: aiosqlite.Connection, name: str) -> int:
    async with conn.execute("SELECT value FROM counters WHERE name=?", (name,)) as cur:
        row = await cur.fetchone()
    if row is None:
        await conn.execute("INSERT INTO counters(name, value) VALUES(?, 1)", (name,))
        await conn.commit()
        return 1
    value = int(row[0]) + 1
    await conn.execute("UPDATE counters SET value=? WHERE name=?", (value, name))
    await conn.commit()
    return value


async def get_counter(conn: aiosqlite.Connection, name: str) -> int:
    async with conn.execute("SELECT value FROM counters WHERE name=?", (name,)) as cur:
        row = await cur.fetchone()
    return int(row[0]) if row else 0
