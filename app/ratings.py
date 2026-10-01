from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
from time import time_ns

import aiosqlite

from app.data import SourceRef, Venue


@dataclass(frozen=True, slots=True)
class CommunityRatingSummary:
    average: float | None
    count: int


def _rating_key(provider: str, source_id: str) -> str:
    return f"{provider}:{source_id}"


def venue_rating_keys(venue: Venue) -> tuple[str, ...]:
    refs = venue.source_refs or (
        SourceRef(
            provider=venue.source,
            source_id=venue.source_id,
            source_url=venue.source_url,
        ),
    )

    keys: list[str] = [_rating_key(venue.source, venue.source_id)]
    keys.extend(_rating_key(ref.provider, ref.source_id) for ref in refs)

    unique: list[str] = []
    seen: set[str] = set()
    for key in keys:
        if key not in seen:
            unique.append(key)
            seen.add(key)
    return tuple(unique)


def canonical_rating_key(venue: Venue) -> str:
    for ref in venue.source_refs:
        if ref.provider == "osm":
            return _rating_key(ref.provider, ref.source_id)
    return _rating_key(venue.source, venue.source_id)


class RatingsRepository:
    def __init__(self, database_path: str) -> None:
        self._database_path = database_path

    async def initialize(self) -> None:
        path = Path(self._database_path)
        path.parent.mkdir(parents=True, exist_ok=True)

        async with aiosqlite.connect(self._database_path) as database:
            await database.execute("PRAGMA journal_mode=WAL")
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
            await database.commit()

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

    async def summary_for_venue(self, venue: Venue) -> CommunityRatingSummary:
        async with aiosqlite.connect(self._database_path) as database:
            return await self._summary_with_database(database, venue)

    async def enrich_many(self, venues: list[Venue]) -> list[Venue]:
        if not venues:
            return []

        async with aiosqlite.connect(self._database_path) as database:
            enriched: list[Venue] = []
            for venue in venues:
                summary = await self._summary_with_database(database, venue)
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

        if not latest_by_user:
            return CommunityRatingSummary(average=None, count=0)

        scores = tuple(latest_by_user.values())
        return CommunityRatingSummary(
            average=sum(scores) / len(scores),
            count=len(scores),
        )
