from __future__ import annotations

from dataclasses import dataclass, replace
from time import time_ns

import aiosqlite

from app.data import Venue
from app.database import initialize_database
from app.identity import canonical_venue_key, venue_identity_keys

MAX_PERSONAL_NOTE_LENGTH = 500
_SQLITE_IN_CHUNK = 900


@dataclass(frozen=True, slots=True)
class PersonalNote:
    text: str
    updated_at_ns: int


def _chunks(values: tuple[str, ...]) -> tuple[tuple[str, ...], ...]:
    return tuple(
        values[index : index + _SQLITE_IN_CHUNK]
        for index in range(0, len(values), _SQLITE_IN_CHUNK)
    )


class NotesRepository:
    """User-owned notes attached to exact provider identities."""

    def __init__(self, database_path: str) -> None:
        self._database_path = database_path

    async def initialize(self) -> None:
        await initialize_database(self._database_path)

    async def get_for_venue(
        self,
        *,
        user_id: int,
        venue: Venue,
    ) -> PersonalNote | None:
        keys = venue_identity_keys(venue)
        placeholders = ",".join("?" for _ in keys)
        async with aiosqlite.connect(self._database_path) as database:
            cursor = await database.execute(
                f"""
                SELECT note, updated_at_ns
                FROM favorite_notes
                WHERE user_id = ?
                  AND identity_key IN ({placeholders})
                ORDER BY updated_at_ns DESC, identity_key ASC
                LIMIT 1
                """,
                (user_id, *keys),
            )
            row = await cursor.fetchone()
            await cursor.close()

        if row is None:
            return None
        note, updated_at_ns = row
        if not isinstance(note, str) or not isinstance(updated_at_ns, int):
            return None
        return PersonalNote(text=note, updated_at_ns=updated_at_ns)

    async def set_note(
        self,
        *,
        user_id: int,
        venue: Venue,
        text: str,
    ) -> PersonalNote:
        normalized = text.strip()
        if not normalized:
            raise ValueError("note must not be empty")
        if len(normalized) > MAX_PERSONAL_NOTE_LENGTH:
            raise ValueError(
                f"note must be at most {MAX_PERSONAL_NOTE_LENGTH} characters"
            )

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
                    raise ValueError("note requires a saved favorite")

                canonical_key = (
                    preferred_key
                    if preferred_key in favorite_keys
                    else next(key for key in keys if key in favorite_keys)
                )
                await database.execute(
                    f"""
                    DELETE FROM favorite_notes
                    WHERE user_id = ?
                      AND identity_key IN ({placeholders})
                    """,
                    (user_id, *keys),
                )
                await database.execute(
                    """
                    INSERT INTO favorite_notes (
                        user_id,
                        identity_key,
                        note,
                        updated_at_ns
                    )
                    VALUES (?, ?, ?, ?)
                    """,
                    (user_id, canonical_key, normalized, updated_at_ns),
                )
                await database.commit()
            except BaseException:
                await database.rollback()
                raise

        return PersonalNote(
            text=normalized,
            updated_at_ns=updated_at_ns,
        )

    async def remove_note(
        self,
        *,
        user_id: int,
        venue: Venue,
    ) -> bool:
        keys = venue_identity_keys(venue)
        placeholders = ",".join("?" for _ in keys)

        async with aiosqlite.connect(self._database_path) as database:
            await database.execute("PRAGMA busy_timeout=5000")
            await database.execute("BEGIN IMMEDIATE")
            try:
                cursor = await database.execute(
                    f"""
                    DELETE FROM favorite_notes
                    WHERE user_id = ?
                      AND identity_key IN ({placeholders})
                    """,
                    (user_id, *keys),
                )
                deleted = cursor.rowcount > 0
                await cursor.close()
                await database.commit()
            except BaseException:
                await database.rollback()
                raise

        return deleted

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

        all_keys = tuple(key_to_indexes)
        rows: list[tuple[object, object, object]] = []
        async with aiosqlite.connect(self._database_path) as database:
            for key_chunk in _chunks(all_keys):
                placeholders = ",".join("?" for _ in key_chunk)
                cursor = await database.execute(
                    f"""
                    SELECT identity_key, note, updated_at_ns
                    FROM favorite_notes
                    WHERE user_id = ?
                      AND identity_key IN ({placeholders})
                    """,
                    (user_id, *key_chunk),
                )
                rows.extend(await cursor.fetchall())
                await cursor.close()

        rows.sort(
            key=lambda row: (
                -(row[2] if isinstance(row[2], int) else 0),
                row[0] if isinstance(row[0], str) else "",
            )
        )

        notes: list[str | None] = [None] * len(venues)
        for identity_key, note, _updated_at_ns in rows:
            if not isinstance(identity_key, str) or not isinstance(note, str):
                continue
            for index in key_to_indexes.get(identity_key, []):
                if notes[index] is None:
                    notes[index] = note

        return [
            replace(venue, personal_note=note)
            for venue, note in zip(venues, notes, strict=True)
        ]
