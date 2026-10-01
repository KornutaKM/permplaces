import json
import sqlite3

import pytest

from app.data import Venue
from app.notes import NotesRepository
from app.privacy import UserDataRepository
from app.ratings import RatingsRepository
from app.storage import FavoritesRepository


def venue(source_id: str) -> Venue:
    return Venue(
        id=f"osm:{source_id}",
        name="Privacy test",
        category="cafe",
        category_label="Кофейня",
        latitude=58.01,
        longitude=56.25,
        source="osm",
        source_id=source_id,
    )


@pytest.mark.asyncio
async def test_user_data_summary_counts_only_requested_user(tmp_path) -> None:
    path = str(tmp_path / "permplaces.db")
    favorites = FavoritesRepository(path)
    ratings = RatingsRepository(path)
    notes = NotesRepository(path)
    repository = UserDataRepository(path)
    await repository.initialize()

    await favorites.toggle(user_id=10, venue=venue("node/1"))
    await favorites.toggle(user_id=11, venue=venue("node/2"))
    await ratings.set_rating(user_id=10, venue=venue("node/1"), score=5)
    await ratings.set_rating(user_id=10, venue=venue("node/3"), score=4)
    await ratings.set_rating(user_id=11, venue=venue("node/2"), score=1)
    await notes.set_note(user_id=10, venue=venue("node/1"), text="Моя заметка")
    await notes.set_note(user_id=11, venue=venue("node/2"), text="Чужая заметка")

    summary = await repository.summary_for_user(user_id=10)

    assert summary.favorites == 1
    assert summary.ratings == 2
    assert summary.notes == 1
    assert summary.total_rows == 4


@pytest.mark.asyncio
async def test_user_data_delete_is_atomic_and_user_scoped(tmp_path) -> None:
    path = str(tmp_path / "permplaces.db")
    favorites = FavoritesRepository(path)
    ratings = RatingsRepository(path)
    notes = NotesRepository(path)
    repository = UserDataRepository(path)
    await repository.initialize()

    await favorites.toggle(user_id=20, venue=venue("node/20"))
    await favorites.toggle(user_id=21, venue=venue("node/21"))
    await ratings.set_rating(user_id=20, venue=venue("node/20"), score=5)
    await ratings.set_rating(user_id=21, venue=venue("node/21"), score=3)
    await notes.set_note(user_id=20, venue=venue("node/20"), text="Удалить")
    await notes.set_note(user_id=21, venue=venue("node/21"), text="Оставить")

    deleted = await repository.delete_for_user(user_id=20)

    assert deleted.favorites == 1
    assert deleted.ratings == 1
    assert deleted.notes == 1
    assert await repository.summary_for_user(user_id=20) == deleted.__class__(0, 0, 0)

    other = await repository.summary_for_user(user_id=21)
    assert other.favorites == 1
    assert other.ratings == 1
    assert other.notes == 1

    with sqlite3.connect(path) as database:
        user_20_aliases = database.execute(
            """
            SELECT COUNT(*)
            FROM favorite_identity_aliases
            WHERE user_id = 20
            """
        ).fetchone()
        user_21_aliases = database.execute(
            """
            SELECT COUNT(*)
            FROM favorite_identity_aliases
            WHERE user_id = 21
            """
        ).fetchone()

    assert user_20_aliases == (0,)
    assert user_21_aliases == (1,)


@pytest.mark.asyncio
async def test_user_data_delete_is_idempotent(tmp_path) -> None:
    path = str(tmp_path / "permplaces.db")
    repository = UserDataRepository(path)
    await repository.initialize()

    first = await repository.delete_for_user(user_id=404)
    second = await repository.delete_for_user(user_id=404)

    assert first.total_rows == 0
    assert second.total_rows == 0


@pytest.mark.asyncio
async def test_user_data_delete_does_not_touch_provider_budget(tmp_path) -> None:
    path = str(tmp_path / "permplaces.db")
    repository = UserDataRepository(path)
    await repository.initialize()

    with sqlite3.connect(path) as database:
        database.execute(
            """
            INSERT INTO provider_daily_request_budget (provider, day, used)
            VALUES ('geoapify', '2026-10-01', 17)
            """
        )
        database.commit()

    await repository.delete_for_user(user_id=1)

    with sqlite3.connect(path) as database:
        used = database.execute(
            """
            SELECT used
            FROM provider_daily_request_budget
            WHERE provider = 'geoapify' AND day = '2026-10-01'
            """
        ).fetchone()

    assert used == (17,)



@pytest.mark.asyncio
async def test_user_data_export_is_scoped_and_omits_telegram_user_id(tmp_path) -> None:
    path = str(tmp_path / "permplaces.db")
    favorites = FavoritesRepository(path)
    ratings = RatingsRepository(path)
    notes = NotesRepository(path)
    repository = UserDataRepository(path)
    await repository.initialize()

    await favorites.toggle(user_id=50, venue=venue("node/export-50"))
    await favorites.toggle(user_id=51, venue=venue("node/export-51"))
    await ratings.set_rating(user_id=50, venue=venue("node/export-50"), score=5)
    await ratings.set_rating(user_id=51, venue=venue("node/export-51"), score=1)
    await notes.set_note(
        user_id=50,
        venue=venue("node/export-50"),
        text="Экспортируемая заметка",
    )
    await notes.set_note(
        user_id=51,
        venue=venue("node/export-51"),
        text="Чужая заметка",
    )

    export = await repository.export_for_user(user_id=50)
    decoded = export.content.decode("utf-8")
    payload = json.loads(decoded)

    assert export.favorites == 1
    assert export.ratings == 1
    assert export.notes == 1
    assert payload["format"] == "permplaces-user-data"
    assert payload["format_version"] == 2
    assert len(payload["favorites"]) == 1
    assert payload["favorites"][0]["venue"]["id"] == "osm:node/export-50"
    assert payload["community_ratings"][0]["venue_key"] == "osm:node/export-50"
    assert payload["community_ratings"][0]["score"] == 5
    assert payload["community_ratings"][0]["updated_at_utc"].endswith("Z")
    assert payload["favorite_notes"][0]["identity_key"] == "osm:node/export-50"
    assert payload["favorite_notes"][0]["note"] == "Экспортируемая заметка"
    assert payload["favorite_notes"][0]["updated_at_utc"].endswith("Z")
    assert '"user_id"' not in decoded
    assert "node/export-51" not in decoded


@pytest.mark.asyncio
async def test_user_data_export_marks_invalid_favorite_payload_without_echoing_it(
    tmp_path,
) -> None:
    path = str(tmp_path / "permplaces.db")
    repository = UserDataRepository(path)
    await repository.initialize()

    with sqlite3.connect(path) as database:
        database.execute(
            """
            INSERT INTO favorites (user_id, venue_id, payload)
            VALUES (60, 'osm:node/corrupt', 'raw-secret-looking-garbage')
            """
        )
        database.commit()

    export = await repository.export_for_user(user_id=60)
    decoded = export.content.decode("utf-8")
    payload = json.loads(decoded)

    assert export.favorites == 1
    assert payload["favorites"][0]["venue_id"] == "osm:node/corrupt"
    assert payload["favorites"][0]["venue"] is None
    assert payload["favorites"][0]["payload_status"] == "invalid"
    assert "raw-secret-looking-garbage" not in decoded
