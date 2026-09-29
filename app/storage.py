from __future__ import annotations

import json
from dataclasses import asdict, replace
from pathlib import Path
from typing import Any

import aiosqlite

from app.data import Venue


def _venue_from_payload(payload: str) -> Venue | None:
    try:
        value: Any = json.loads(payload)
    except json.JSONDecodeError:
        return None

    if not isinstance(value, dict):
        return None

    cuisine = value.get("cuisine")
    if isinstance(cuisine, list):
        value["cuisine"] = tuple(str(item) for item in cuisine)

    try:
        return Venue(**value)
    except TypeError:
        return None


class FavoritesRepository:
    def __init__(self, database_path: str) -> None:
        self._database_path = database_path

    async def initialize(self) -> None:
        path = Path(self._database_path)
        path.parent.mkdir(parents=True, exist_ok=True)

        async with aiosqlite.connect(self._database_path) as database:
            await database.execute("PRAGMA journal_mode=WAL")
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
            await database.commit()

    async def toggle(self, *, user_id: int, venue: Venue) -> bool:
        async with aiosqlite.connect(self._database_path) as database:
            await database.execute("PRAGMA busy_timeout=5000")
            await database.execute("BEGIN IMMEDIATE")
            cursor = await database.execute(
                "SELECT 1 FROM favorites WHERE user_id = ? AND venue_id = ?",
                (user_id, venue.id),
            )
            exists = await cursor.fetchone()
            await cursor.close()

            if exists:
                await database.execute(
                    "DELETE FROM favorites WHERE user_id = ? AND venue_id = ?",
                    (user_id, venue.id),
                )
                await database.commit()
                return False

            persistent_venue = replace(venue, distance_m=None)
            payload = json.dumps(
                asdict(persistent_venue),
                ensure_ascii=False,
                separators=(",", ":"),
            )
            await database.execute(
                """
                INSERT INTO favorites (user_id, venue_id, payload)
                VALUES (?, ?, ?)
                """,
                (user_id, venue.id, payload),
            )
            await database.commit()
            return True

    async def list_for_user(self, *, user_id: int) -> list[Venue]:
        async with aiosqlite.connect(self._database_path) as database:
            cursor = await database.execute(
                """
                SELECT payload
                FROM favorites
                WHERE user_id = ?
                ORDER BY created_at DESC, venue_id ASC
                """,
                (user_id,),
            )
            rows = await cursor.fetchall()
            await cursor.close()

        venues: list[Venue] = []
        for (payload,) in rows:
            if not isinstance(payload, str):
                continue
            venue = _venue_from_payload(payload)
            if venue is not None:
                venues.append(venue)
        return venues
