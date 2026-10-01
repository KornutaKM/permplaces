from __future__ import annotations

from dataclasses import dataclass, replace
from time import time_ns

import aiosqlite

from app.data import Venue
from app.database import initialize_database
from app.identity import canonical_venue_key, venue_identity_keys


@dataclass(frozen=True, slots=True)
class CommunityRatingSummary:
    average: float | None
    count: int


def venue_rating_keys(venue: Venue) -> tuple[str, ...]:
    return venue_identity_keys(venue)


def canonical_rating_key(venue: Venue) -> str:
    return canonical_venue_key(venue)


def _summary_from_scores(scores: dict[int, int]) -> CommunityRatingSummary:
    if not scores:
        return CommunityRatingSummary(average=None, count=0)
    values = tuple(scores.values())
    return CommunityRatingSummary(
        average=sum(values) / len(values),
        count=len(values),
    )


_SQLITE_IN_CHUNK = 900


def _chunks(values: tuple[str, ...], size: int = _SQLITE_IN_CHUNK) -> tuple[tuple[str, ...], ...]:
    return tuple(values[index : index + size] for index in range(0, len(values), size))


class RatingsRepository:
    def __init__(self, database_path: str) -> None:
        self._database_path = database_path

    async def initialize(self) -> None:
        await initialize_database(self._database_path)

    async def set_rating(
        self,
        *,
        user_id: int,
        venue: Venue,
        score: int,
    ) -> CommunityRatingSummary:
        if isinstance(score, bool) or not isinstance(score, int) or not 1 <= score <= 5:
            raise ValueError("score must be an integer from 1 to 5")

        key = canonical_rating_key(venue)
        async with aiosqlite.connect(self._database_path) as database:
            await database.execute("PRAGMA busy_timeout=5000")
            await database.execute("BEGIN IMMEDIATE")
            await database.execute(
                """
                INSERT INTO venue_ratings (user_id, venue_key, score, updated_at_ns)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(user_id, venue_key) DO UPDATE SET
                    score = excluded.score,
                    updated_at_ns = excluded.updated_at_ns
                """,
                (user_id, key, score, time_ns()),
            )
            await database.commit()
            return await self._summary_with_database(database, venue)

    async def remove_rating(
        self,
        *,
        user_id: int,
        venue: Venue,
    ) -> CommunityRatingSummary:
        keys = venue_rating_keys(venue)
        placeholders = ",".join("?" for _ in keys)

        async with aiosqlite.connect(self._database_path) as database:
            await database.execute("PRAGMA busy_timeout=5000")
            await database.execute("BEGIN IMMEDIATE")
            await database.execute(
                f"""
                DELETE FROM venue_ratings
                WHERE user_id = ?
                  AND venue_key IN ({placeholders})
                """,
                (user_id, *keys),
            )
            await database.commit()
            return await self._summary_with_database(database, venue)

    async def user_rating_for_venue(
        self,
        *,
        user_id: int,
        venue: Venue,
    ) -> int | None:
        keys = venue_rating_keys(venue)
        placeholders = ",".join("?" for _ in keys)

        async with aiosqlite.connect(self._database_path) as database:
            cursor = await database.execute(
                f"""
                SELECT score
                FROM venue_ratings
                WHERE user_id = ?
                  AND venue_key IN ({placeholders})
                ORDER BY updated_at_ns DESC, venue_key ASC
                LIMIT 1
                """,
                (user_id, *keys),
            )
            row = await cursor.fetchone()
            await cursor.close()

        if row is None:
            return None
        score = row[0]
        if isinstance(score, int) and not isinstance(score, bool) and 1 <= score <= 5:
            return score
        return None

    async def summary_for_venue(self, venue: Venue) -> CommunityRatingSummary:
        async with aiosqlite.connect(self._database_path) as database:
            return await self._summary_with_database(database, venue)

    async def enrich_many(self, venues: list[Venue]) -> list[Venue]:
        if not venues:
            return []

        keys_by_index = [venue_rating_keys(venue) for venue in venues]
        key_to_indexes: dict[str, list[int]] = {}
        for index, keys in enumerate(keys_by_index):
            for key in keys:
                key_to_indexes.setdefault(key, []).append(index)

        all_keys = tuple(key_to_indexes)
        rows: list[tuple[object, object, object, object]] = []
        async with aiosqlite.connect(self._database_path) as database:
            for key_chunk in _chunks(all_keys):
                placeholders = ",".join("?" for _ in key_chunk)
                cursor = await database.execute(
                    f"""
                    SELECT venue_key, user_id, score, updated_at_ns
                    FROM venue_ratings
                    WHERE venue_key IN ({placeholders})
                    """,
                    key_chunk,
                )
                rows.extend(await cursor.fetchall())
                await cursor.close()

        rows.sort(
            key=lambda row: (
                -(row[3] if isinstance(row[3], int) else 0),
                row[0] if isinstance(row[0], str) else "",
            )
        )

        latest_by_venue: list[dict[int, int]] = [{} for _ in venues]
        for venue_key, user_id, score, _updated_at_ns in rows:
            if not isinstance(venue_key, str) or venue_key not in key_to_indexes:
                continue
            if not isinstance(user_id, int):
                continue
            if isinstance(score, bool) or not isinstance(score, int) or not 1 <= score <= 5:
                continue
            for index in key_to_indexes[venue_key]:
                latest_by_venue[index].setdefault(user_id, score)

        enriched: list[Venue] = []
        for venue, scores in zip(venues, latest_by_venue, strict=True):
            summary = _summary_from_scores(scores)
            enriched.append(
                replace(
                    venue,
                    community_rating=summary.average,
                    community_rating_count=summary.count or None,
                )
            )
        return enriched

    async def _summary_with_database(
        self,
        database: aiosqlite.Connection,
        venue: Venue,
    ) -> CommunityRatingSummary:
        keys = venue_rating_keys(venue)
        placeholders = ",".join("?" for _ in keys)
        cursor = await database.execute(
            f"""
            SELECT user_id, score, updated_at_ns
            FROM venue_ratings
            WHERE venue_key IN ({placeholders})
            ORDER BY updated_at_ns DESC, venue_key ASC
            """,
            keys,
        )
        rows = await cursor.fetchall()
        await cursor.close()

        latest_by_user: dict[int, int] = {}
        for user_id, score, _updated_at_ns in rows:
            if not isinstance(user_id, int) or user_id in latest_by_user:
                continue
            if isinstance(score, int) and not isinstance(score, bool) and 1 <= score <= 5:
                latest_by_user[user_id] = score

        return _summary_from_scores(latest_by_user)
