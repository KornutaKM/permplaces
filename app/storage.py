from __future__ import annotations

import json
from dataclasses import asdict, replace
from typing import Any

import aiosqlite

from app.data import FieldSource, PhotoRef, SourceRef, Venue
from app.database import initialize_database
from app.identity import venue_identity_keys


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

    source_refs = value.get("source_refs")
    if isinstance(source_refs, list):
        value["source_refs"] = tuple(
            SourceRef(**item)
            for item in source_refs
            if isinstance(item, dict)
        )

    field_sources = value.get("field_sources")
    if isinstance(field_sources, list):
        value["field_sources"] = tuple(
            FieldSource(**item)
            for item in field_sources
            if isinstance(item, dict)
        )

    photos = value.get("photos")
    if isinstance(photos, list):
        value["photos"] = tuple(
            PhotoRef(**item)
            for item in photos
            if isinstance(item, dict)
        )

    personal_tags = value.get("personal_tags")
    if isinstance(personal_tags, list):
        value["personal_tags"] = tuple(str(item) for item in personal_tags)

    try:
        return Venue(**value)
    except TypeError:
        return None


class FavoritesRepository:
    def __init__(self, database_path: str) -> None:
        self._database_path = database_path

    async def initialize(self) -> None:
        await initialize_database(self._database_path)

    async def toggle(self, *, user_id: int, venue: Venue) -> bool:
        target_keys = venue_identity_keys(venue)
        placeholders = ",".join("?" for _ in target_keys)

        async with aiosqlite.connect(self._database_path) as database:
            await database.execute("PRAGMA busy_timeout=5000")
            await database.execute("BEGIN IMMEDIATE")
            try:
                cursor = await database.execute(
                    f"""
                    SELECT DISTINCT venue_id
                    FROM favorite_identity_aliases
                    WHERE user_id = ?
                      AND identity_key IN ({placeholders})
                    """,
                    (user_id, *target_keys),
                )
                matching_ids = [
                    row[0]
                    for row in await cursor.fetchall()
                    if row and isinstance(row[0], str)
                ]
                await cursor.close()

                if matching_ids:
                    note_keys = set(target_keys)
                    for stored_id in matching_ids:
                        alias_cursor = await database.execute(
                            """
                            SELECT identity_key
                            FROM favorite_identity_aliases
                            WHERE user_id = ? AND venue_id = ?
                            """,
                            (user_id, stored_id),
                        )
                        note_keys.update(
                            row[0]
                            for row in await alias_cursor.fetchall()
                            if row and isinstance(row[0], str)
                        )
                        await alias_cursor.close()

                    note_placeholders = ",".join("?" for _ in note_keys)
                    await database.execute(
                        f"""
                        DELETE FROM favorite_notes
                        WHERE user_id = ?
                          AND identity_key IN ({note_placeholders})
                        """,
                        (user_id, *sorted(note_keys)),
                    )
                    await database.execute(
                        f"""
                        DELETE FROM favorite_tags
                        WHERE user_id = ?
                          AND identity_key IN ({note_placeholders})
                        """,
                        (user_id, *sorted(note_keys)),
                    )

                    for stored_id in matching_ids:
                        await database.execute(
                            """
                            DELETE FROM favorites
                            WHERE user_id = ? AND venue_id = ?
                            """,
                            (user_id, stored_id),
                        )
                        await database.execute(
                            """
                            DELETE FROM favorite_identity_aliases
                            WHERE user_id = ? AND venue_id = ?
                            """,
                            (user_id, stored_id),
                        )
                    await database.commit()
                    return False

                persistent_venue = replace(
                    venue,
                    distance_m=None,
                    is_open_now=None,
                    is_open_late=None,
                    community_rating=None,
                    community_rating_count=None,
                    personal_note=None,
                    personal_tags=(),
                )
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
                await database.executemany(
                    """
                    INSERT INTO favorite_identity_aliases (
                        user_id,
                        venue_id,
                        identity_key
                    )
                    VALUES (?, ?, ?)
                    """,
                    [
                        (user_id, venue.id, identity_key)
                        for identity_key in target_keys
                    ],
                )
                await database.commit()
                return True
            except BaseException:
                await database.rollback()
                raise

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
        seen_keys: set[str] = set()
        for (payload,) in rows:
            if not isinstance(payload, str):
                continue
            venue = _venue_from_payload(payload)
            if venue is None:
                continue

            keys = set(venue_identity_keys(venue))
            if seen_keys.intersection(keys):
                seen_keys.update(keys)
                continue

            venues.append(venue)
            seen_keys.update(keys)
        return venues
