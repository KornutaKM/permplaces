from __future__ import annotations

import json
from pathlib import Path

import aiosqlite

SCHEMA_VERSION = 2


class DatabaseSchemaError(RuntimeError):
    pass


async def _table_columns(
    database: aiosqlite.Connection,
    table_name: str,
) -> set[str]:
    cursor = await database.execute(f'PRAGMA table_info("{table_name}")')
    rows = await cursor.fetchall()
    await cursor.close()
    return {
        str(row[1])
        for row in rows
        if len(row) > 1 and isinstance(row[1], str)
    }


async def _require_columns(
    database: aiosqlite.Connection,
    table_name: str,
    required: set[str],
) -> None:
    columns = await _table_columns(database, table_name)
    missing = sorted(required - columns)
    if missing:
        raise DatabaseSchemaError(
            f"table {table_name} is missing required columns: {', '.join(missing)}"
        )


def _favorite_identity_keys(venue_id: str, payload: str) -> tuple[str, ...]:
    keys: list[str] = []
    if venue_id:
        keys.append(venue_id)

    try:
        value = json.loads(payload)
    except json.JSONDecodeError:
        value = None

    if isinstance(value, dict):
        source = value.get("source")
        source_id = value.get("source_id")
        if isinstance(source, str) and isinstance(source_id, str):
            keys.append(f"{source}:{source_id}")

        source_refs = value.get("source_refs")
        if isinstance(source_refs, list):
            for ref in source_refs:
                if not isinstance(ref, dict):
                    continue
                provider = ref.get("provider")
                ref_source_id = ref.get("source_id")
                if isinstance(provider, str) and isinstance(ref_source_id, str):
                    keys.append(f"{provider}:{ref_source_id}")

    unique: list[str] = []
    seen: set[str] = set()
    for key in keys:
        if key and key not in seen:
            unique.append(key)
            seen.add(key)
    return tuple(unique)


async def _backfill_favorite_aliases(database: aiosqlite.Connection) -> None:
    await database.execute("DELETE FROM favorite_identity_aliases")
    cursor = await database.execute(
        """
        SELECT user_id, venue_id, payload
        FROM favorites
        ORDER BY user_id, created_at, venue_id
        """
    )
    rows = await cursor.fetchall()
    await cursor.close()

    for user_id, venue_id, payload in rows:
        if not isinstance(user_id, int):
            continue
        if not isinstance(venue_id, str) or not isinstance(payload, str):
            continue
        for identity_key in _favorite_identity_keys(venue_id, payload):
            await database.execute(
                """
                INSERT OR IGNORE INTO favorite_identity_aliases (
                    user_id,
                    venue_id,
                    identity_key
                )
                VALUES (?, ?, ?)
                """,
                (user_id, venue_id, identity_key),
            )


async def initialize_database(database_path: str) -> None:
    """Create or migrate the application SQLite schema transactionally."""

    path = Path(database_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    async with aiosqlite.connect(database_path) as database:
        await database.execute("PRAGMA busy_timeout=5000")
        await database.execute("PRAGMA journal_mode=WAL")

        cursor = await database.execute("PRAGMA user_version")
        row = await cursor.fetchone()
        await cursor.close()
        current_version = int(row[0]) if row else 0

        if current_version > SCHEMA_VERSION:
            raise DatabaseSchemaError(
                "database schema is newer than this application "
                f"({current_version} > {SCHEMA_VERSION})"
            )

        await database.execute("BEGIN IMMEDIATE")
        try:
            await database.execute(
                """
                CREATE TABLE IF NOT EXISTS favorites (
                    user_id INTEGER NOT NULL,
                    venue_id TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (user_id, venue_id)
                )
                """
            )
            await database.execute(
                """
                CREATE TABLE IF NOT EXISTS venue_ratings (
                    user_id INTEGER NOT NULL,
                    venue_key TEXT NOT NULL,
                    score INTEGER NOT NULL CHECK (score BETWEEN 1 AND 5),
                    updated_at_ns INTEGER NOT NULL,
                    PRIMARY KEY (user_id, venue_key)
                )
                """
            )
            await _require_columns(
                database,
                "favorites",
                {"user_id", "venue_id", "payload", "created_at"},
            )
            await _require_columns(
                database,
                "venue_ratings",
                {"user_id", "venue_key", "score", "updated_at_ns"},
            )
            await database.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_venue_ratings_venue_key
                ON venue_ratings (venue_key, updated_at_ns DESC)
                """
            )
            await database.execute(
                """
                CREATE TABLE IF NOT EXISTS provider_daily_request_budget (
                    provider TEXT NOT NULL,
                    day TEXT NOT NULL,
                    used INTEGER NOT NULL CHECK (used >= 0),
                    PRIMARY KEY (provider, day)
                )
                """
            )
            await _require_columns(
                database,
                "provider_daily_request_budget",
                {"provider", "day", "used"},
            )
            await database.execute(
                """
                CREATE TABLE IF NOT EXISTS favorite_identity_aliases (
                    user_id INTEGER NOT NULL,
                    venue_id TEXT NOT NULL,
                    identity_key TEXT NOT NULL,
                    PRIMARY KEY (user_id, venue_id, identity_key)
                )
                """
            )
            await _require_columns(
                database,
                "favorite_identity_aliases",
                {"user_id", "venue_id", "identity_key"},
            )
            await database.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_favorite_identity_aliases_lookup
                ON favorite_identity_aliases (user_id, identity_key, venue_id)
                """
            )

            if current_version < 2:
                await _backfill_favorite_aliases(database)

            await database.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
            await database.commit()
        except BaseException:
            await database.rollback()
            raise
