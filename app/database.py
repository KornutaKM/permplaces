from __future__ import annotations

from pathlib import Path

import aiosqlite

SCHEMA_VERSION = 1


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
                "favorites",
                {"user_id", "venue_id", "payload", "created_at"},
            )
            await _require_columns(
                database,
                "venue_ratings",
                {"user_id", "venue_key", "score", "updated_at_ns"},
            )
            await _require_columns(
                database,
                "provider_daily_request_budget",
                {"provider", "day", "used"},
            )

            await database.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
            await database.commit()
        except BaseException:
            await database.rollback()
            raise
