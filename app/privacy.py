from __future__ import annotations

from dataclasses import dataclass

import aiosqlite

from app.database import initialize_database


@dataclass(frozen=True, slots=True)
class UserDataSummary:
    favorites: int
    ratings: int

    @property
    def total_rows(self) -> int:
        return self.favorites + self.ratings


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
