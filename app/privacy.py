from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime

import aiosqlite

from app.database import initialize_database

USER_DATA_EXPORT_FILENAME = "permplaces-mydata.json"
USER_DATA_EXPORT_FORMAT_VERSION = 1


@dataclass(frozen=True, slots=True)
class UserDataSummary:
    favorites: int
    ratings: int

    @property
    def total_rows(self) -> int:
        return self.favorites + self.ratings


@dataclass(frozen=True, slots=True)
class UserDataExport:
    content: bytes
    favorites: int
    ratings: int


def _rating_updated_at_utc(value: object) -> str | None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    try:
        updated_at = datetime.fromtimestamp(value / 1_000_000_000, tz=UTC)
    except (OSError, OverflowError, ValueError):
        return None
    return updated_at.isoformat().replace("+00:00", "Z")


def _favorite_export_item(
    *,
    venue_id: object,
    payload: object,
    created_at: object,
) -> dict[str, object]:
    item: dict[str, object] = {
        "venue_id": venue_id if isinstance(venue_id, str) else None,
        "saved_at_utc": created_at if isinstance(created_at, str) else None,
        "venue": None,
    }
    if not isinstance(payload, str):
        item["payload_status"] = "invalid"
        return item

    try:
        value = json.loads(payload)
    except json.JSONDecodeError:
        item["payload_status"] = "invalid"
        return item

    if isinstance(value, dict):
        item["venue"] = value
        item["payload_status"] = "ok"
    else:
        item["payload_status"] = "invalid"
    return item


class UserDataRepository:
    """Account-scoped application data controls for the PermPlaces SQLite DB."""

    def __init__(self, database_path: str) -> None:
        self._database_path = database_path

    async def initialize(self) -> None:
        await initialize_database(self._database_path)

    async def summary_for_user(self, *, user_id: int) -> UserDataSummary:
        async with aiosqlite.connect(self._database_path) as database:
            favorite_cursor = await database.execute(
                "SELECT COUNT(*) FROM favorites WHERE user_id = ?",
                (user_id,),
            )
            favorite_row = await favorite_cursor.fetchone()
            await favorite_cursor.close()

            rating_cursor = await database.execute(
                "SELECT COUNT(*) FROM venue_ratings WHERE user_id = ?",
                (user_id,),
            )
            rating_row = await rating_cursor.fetchone()
            await rating_cursor.close()

        return UserDataSummary(
            favorites=int(favorite_row[0]) if favorite_row is not None else 0,
            ratings=int(rating_row[0]) if rating_row is not None else 0,
        )

    async def export_for_user(self, *, user_id: int) -> UserDataExport:
        """Return a user-scoped JSON export without embedding the Telegram user ID."""

        async with aiosqlite.connect(self._database_path) as database:
            await database.execute("BEGIN")
            try:
                favorite_cursor = await database.execute(
                    """
                    SELECT venue_id, payload, created_at
                    FROM favorites
                    WHERE user_id = ?
                    ORDER BY created_at ASC, venue_id ASC
                    """,
                    (user_id,),
                )
                favorite_rows = await favorite_cursor.fetchall()
                await favorite_cursor.close()

                rating_cursor = await database.execute(
                    """
                    SELECT venue_key, score, updated_at_ns
                    FROM venue_ratings
                    WHERE user_id = ?
                    ORDER BY updated_at_ns ASC, venue_key ASC
                    """,
                    (user_id,),
                )
                rating_rows = await rating_cursor.fetchall()
                await rating_cursor.close()
                await database.commit()
            except BaseException:
                await database.rollback()
                raise

        favorites = [
            _favorite_export_item(
                venue_id=venue_id,
                payload=payload,
                created_at=created_at,
            )
            for venue_id, payload, created_at in favorite_rows
        ]
        ratings = [
            {
                "venue_key": venue_key if isinstance(venue_key, str) else None,
                "score": (
                    score
                    if isinstance(score, int)
                    and not isinstance(score, bool)
                    and 1 <= score <= 5
                    else None
                ),
                "updated_at_utc": _rating_updated_at_utc(updated_at_ns),
            }
            for venue_key, score, updated_at_ns in rating_rows
        ]

        payload = {
            "format": "permplaces-user-data",
            "format_version": USER_DATA_EXPORT_FORMAT_VERSION,
            "favorites": favorites,
            "community_ratings": ratings,
        }
        content = (
            json.dumps(
                payload,
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            + "\n"
        ).encode("utf-8")

        return UserDataExport(
            content=content,
            favorites=len(favorites),
            ratings=len(ratings),
        )

    async def delete_for_user(self, *, user_id: int) -> UserDataSummary:
        """Delete favorites and community ratings in one SQLite transaction."""

        async with aiosqlite.connect(self._database_path) as database:
            await database.execute("PRAGMA busy_timeout=5000")
            await database.execute("BEGIN IMMEDIATE")
            try:
                favorite_cursor = await database.execute(
                    "SELECT COUNT(*) FROM favorites WHERE user_id = ?",
                    (user_id,),
                )
                favorite_row = await favorite_cursor.fetchone()
                await favorite_cursor.close()

                rating_cursor = await database.execute(
                    "SELECT COUNT(*) FROM venue_ratings WHERE user_id = ?",
                    (user_id,),
                )
                rating_row = await rating_cursor.fetchone()
                await rating_cursor.close()

                await database.execute(
                    "DELETE FROM favorite_identity_aliases WHERE user_id = ?",
                    (user_id,),
                )
                await database.execute(
                    "DELETE FROM favorites WHERE user_id = ?",
                    (user_id,),
                )
                await database.execute(
                    "DELETE FROM venue_ratings WHERE user_id = ?",
                    (user_id,),
                )
                await database.commit()
            except BaseException:
                await database.rollback()
                raise

        return UserDataSummary(
            favorites=int(favorite_row[0]) if favorite_row is not None else 0,
            ratings=int(rating_row[0]) if rating_row is not None else 0,
        )
