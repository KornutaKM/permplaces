from __future__ import annotations

from dataclasses import replace
from time import time_ns

import aiosqlite

from app.data import Venue
from app.database import initialize_database
from app.identity import canonical_venue_key, venue_identity_keys

FAVORITE_TAG_LABELS: dict[str, str] = {
    "want": "📌 Хочу сходить",
    "return": "🔁 Вернуться",
    "work": "💻 Для работы",
    "family": "👨‍👩‍👧 С семьёй",
    "friends": "👥 С друзьями",
}
FAVORITE_TAG_KEYS = tuple(FAVORITE_TAG_LABELS)
_SQLITE_IN_CHUNK = 900


def favorite_tag_label(tag: str) -> str:
    return FAVORITE_TAG_LABELS[tag]


def _chunks(values: tuple[str, ...]) -> tuple[tuple[str, ...], ...]:
    return tuple(
        values[index : index + _SQLITE_IN_CHUNK]
        for index in range(0, len(values), _SQLITE_IN_CHUNK)
    )


class FavoriteTagsRepository:
    """User-selected organizational tags for exact favorite identities."""

    def __init__(self, database_path: str) -> None:
        self._database_path = database_path

    async def initialize(self) -> None:
        await initialize_database(self._database_path)

    async def tags_for_venue(
        self,
        *,
        user_id: int,
        venue: Venue,
    ) -> tuple[str, ...]:
        keys = venue_identity_keys(venue)
        placeholders = ",".join("?" for _ in keys)
        async with aiosqlite.connect(self._database_path) as database:
            cursor = await database.execute(
                f"""
                SELECT tag
                FROM favorite_tags
                WHERE user_id = ?
                  AND identity_key IN ({placeholders})
                """,
                (user_id, *keys),
            )
            rows = await cursor.fetchall()
            await cursor.close()

        found = {
            row[0]
            for row in rows
            if row and isinstance(row[0], str) and row[0] in FAVORITE_TAG_LABELS
        }
        return tuple(tag for tag in FAVORITE_TAG_KEYS if tag in found)

    async def toggle_tag(
        self,
        *,
        user_id: int,
        venue: Venue,
        tag: str,
    ) -> bool:
        if tag not in FAVORITE_TAG_LABELS:
            raise ValueError("unsupported favorite tag")

        keys = venue_identity_keys(venue)
        placeholders = ",".join("?" for _ in keys)
        preferred_key = canonical_venue_key(venue)
        updated_at_ns = time_ns()

        async with aiosqlite.connect(self._database_path) as database:
            await database.execute("PRAGMA busy_timeout=5000")
            await database.execute("BEGIN IMMEDIATE")
            try:
                alias_cursor = await database.execute(
                    f"""
                    SELECT identity_key
                    FROM favorite_identity_aliases
                    WHERE user_id = ?
                      AND identity_key IN ({placeholders})
                    """,
                    (user_id, *keys),
                )
                favorite_keys = {
                    row[0]
                    for row in await alias_cursor.fetchall()
                    if row and isinstance(row[0], str)
                }
                await alias_cursor.close()
                if not favorite_keys:
                    raise ValueError("tag requires a saved favorite")

                canonical_key = (
                    preferred_key
                    if preferred_key in favorite_keys
                    else next(key for key in keys if key in favorite_keys)
                )

                existing_cursor = await database.execute(
                    f"""
                    SELECT 1
                    FROM favorite_tags
                    WHERE user_id = ?
                      AND tag = ?
                      AND identity_key IN ({placeholders})
                    LIMIT 1
                    """,
                    (user_id, tag, *keys),
                )
                existed = await existing_cursor.fetchone() is not None
                await existing_cursor.close()

                await database.execute(
                    f"""
                    DELETE FROM favorite_tags
                    WHERE user_id = ?
                      AND tag = ?
                      AND identity_key IN ({placeholders})
                    """,
                    (user_id, tag, *keys),
                )

                if not existed:
                    await database.execute(
                        """
                        INSERT INTO favorite_tags (
                            user_id,
                            identity_key,
                            tag,
                            updated_at_ns
                        )
                        VALUES (?, ?, ?, ?)
                        """,
                        (user_id, canonical_key, tag, updated_at_ns),
                    )

                await database.commit()
            except BaseException:
                await database.rollback()
                raise

        return not existed

    async def enrich_many(
        self,
        *,
        user_id: int,
        venues: list[Venue],
    ) -> list[Venue]:
        if not venues:
            return []

        key_to_indexes: dict[str, list[int]] = {}
        for index, venue in enumerate(venues):
            for key in venue_identity_keys(venue):
                key_to_indexes.setdefault(key, []).append(index)

        rows: list[tuple[object, object]] = []
        all_keys = tuple(key_to_indexes)
        async with aiosqlite.connect(self._database_path) as database:
            for key_chunk in _chunks(all_keys):
                placeholders = ",".join("?" for _ in key_chunk)
                cursor = await database.execute(
                    f"""
                    SELECT identity_key, tag
                    FROM favorite_tags
                    WHERE user_id = ?
                      AND identity_key IN ({placeholders})
                    """,
                    (user_id, *key_chunk),
                )
                rows.extend(await cursor.fetchall())
                await cursor.close()

        tags_by_index: list[set[str]] = [set() for _ in venues]
        for identity_key, tag in rows:
            if (
                not isinstance(identity_key, str)
                or not isinstance(tag, str)
                or tag not in FAVORITE_TAG_LABELS
            ):
                continue
            for index in key_to_indexes.get(identity_key, []):
                tags_by_index[index].add(tag)

        return [
            replace(
                venue,
                personal_tags=tuple(
                    tag for tag in FAVORITE_TAG_KEYS if tag in tags_by_index[index]
                ),
            )
            for index, venue in enumerate(venues)
        ]


def favorite_tag_counts(venues: list[Venue]) -> dict[str, int]:
    counts = {tag: 0 for tag in FAVORITE_TAG_KEYS}
    for venue in venues:
        for tag in set(venue.personal_tags):
            if tag in counts:
                counts[tag] += 1
    return counts
