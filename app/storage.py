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
        target_keys = set(venue_identity_keys(venue))

        async with aiosqlite.connect(self._database_path) as database:
            await database.execute("PRAGMA busy_timeout=5000")
            await database.execute("BEGIN IMMEDIATE")
            try:
                cursor = await database.execute(
                    """
                    SELECT venue_id, payload
                    FROM favorites
                    WHERE user_id = ?
                    """,
                    (user_id,),
                )
                rows = await cursor.fetchall()
                await cursor.close()

                matching_ids: list[str] = []
                for stored_id, payload in rows:
                    if not isinstance(stored_id, str):
                        continue
                    if stored_id == venue.id:
                        matching_ids.append(stored_id)
                        continue
                    if not isinstance(payload, str):
                        continue
                    stored = _venue_from_payload(payload)
                    if stored is None:
                        continue
                    if target_keys.intersection(venue_identity_keys(stored)):
                        matching_ids.append(stored_id)

                if matching_ids:
                    for stored_id in matching_ids:
                        await database.execute(
                            """
                            DELETE FROM favorites
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
