import asyncio
import json
import sqlite3
from dataclasses import asdict

import pytest

from app.data import FieldSource, PhotoRef, SourceRef, Venue
from app.notes import NotesRepository
from app.storage import FavoritesRepository


@pytest.mark.asyncio
async def test_favorites_survive_repository_recreation(tmp_path) -> None:
    database_path = tmp_path / "permplaces.db"
    venue = Venue(
        id="osm:node/42",
        name="Кофейня",
        category="cafe",
        category_label="Кофейня",
        latitude=58.01,
        longitude=56.25,
        source="osm",
        source_id="node/42",
        cuisine=("coffee_shop",),
        distance_m=350,
        is_open_now=True,
        is_open_late=True,
        community_rating=4.5,
        community_rating_count=12,
        personal_note="transient note",
    )

    repository = FavoritesRepository(str(database_path))
    await repository.initialize()

    added = await repository.toggle(user_id=100, venue=venue)
    assert added is True

    recreated = FavoritesRepository(str(database_path))
    await recreated.initialize()
    favorites = await recreated.list_for_user(user_id=100)

    assert len(favorites) == 1
    assert favorites[0].id == venue.id
    assert favorites[0].cuisine == ("coffee_shop",)
    assert favorites[0].distance_m is None
    assert favorites[0].is_open_now is None
    assert favorites[0].is_open_late is None
    assert favorites[0].community_rating is None
    assert favorites[0].community_rating_count is None
    assert favorites[0].personal_note is None


@pytest.mark.asyncio
async def test_toggle_removes_existing_favorite(tmp_path) -> None:
    database_path = tmp_path / "permplaces.db"
    venue = Venue(
        id="osm:way/7",
        name="Ресторан",
        category="restaurant",
        category_label="Ресторан",
        latitude=58.02,
        longitude=56.26,
        source="osm",
        source_id="way/7",
    )

    repository = FavoritesRepository(str(database_path))
    await repository.initialize()

    assert await repository.toggle(user_id=1, venue=venue) is True
    assert await repository.toggle(user_id=1, venue=venue) is False
    assert await repository.list_for_user(user_id=1) == []


@pytest.mark.asyncio
async def test_favorites_are_isolated_per_user(tmp_path) -> None:
    database_path = tmp_path / "permplaces.db"
    venue = Venue(
        id="osm:node/9",
        name="Бар",
        category="bar",
        category_label="Бар",
        latitude=58.0,
        longitude=56.2,
        source="osm",
        source_id="node/9",
    )

    repository = FavoritesRepository(str(database_path))
    await repository.initialize()
    await repository.toggle(user_id=10, venue=venue)

    assert len(await repository.list_for_user(user_id=10)) == 1
    assert await repository.list_for_user(user_id=11) == []


@pytest.mark.asyncio
async def test_concurrent_double_toggle_is_serialized(tmp_path) -> None:
    database_path = tmp_path / "permplaces.db"
    venue = Venue(
        id="osm:node/77",
        name="Кофейня",
        category="cafe",
        category_label="Кофейня",
        latitude=58.01,
        longitude=56.25,
        source="osm",
        source_id="node/77",
    )

    repository = FavoritesRepository(str(database_path))
    await repository.initialize()

    results = await asyncio.gather(
        repository.toggle(user_id=5, venue=venue),
        repository.toggle(user_id=5, venue=venue),
    )

    assert sorted(results) == [False, True]
    assert await repository.list_for_user(user_id=5) == []



@pytest.mark.asyncio
async def test_favorites_round_trip_multi_provider_provenance(tmp_path) -> None:
    database_path = tmp_path / "permplaces.db"
    venue = Venue(
        id="osm:node/500",
        name="Объединённое место",
        category="cafe",
        category_label="Кофейня",
        latitude=58.01,
        longitude=56.25,
        source="osm",
        source_id="node/500",
        source_refs=(
            SourceRef("osm", "node/500", "https://www.openstreetmap.org/node/500"),
            SourceRef("catalog", "abc-500", "https://example.test/place/abc-500"),
        ),
        field_sources=(
            FieldSource("name", "osm", "node/500"),
            FieldSource("rating", "catalog", "abc-500"),
        ),
        rating=4.8,
        review_count=150,
        menu_url="https://menu.example.test/place",
        photos=(
            PhotoRef(
                provider="foursquare",
                source_id="photo-500",
                url="https://images.example.test/original/500.jpg",
                attribution="Powered by Foursquare",
            ),
        ),
    )

    repository = FavoritesRepository(str(database_path))
    await repository.initialize()
    assert await repository.toggle(user_id=50, venue=venue) is True

    restored = (await repository.list_for_user(user_id=50))[0]

    assert restored.source_refs == venue.source_refs
    assert restored.field_sources == venue.field_sources
    assert restored.rating == 4.8
    assert restored.review_count == 150
    assert restored.menu_url == "https://menu.example.test/place"
    assert restored.photos == venue.photos



def aliased_venues() -> tuple[Venue, Venue]:
    geo = Venue(
        id="geoapify:place-alias",
        name="Alias cafe",
        category="cafe",
        category_label="Кофейня",
        latitude=58.01,
        longitude=56.25,
        source="geoapify",
        source_id="place-alias",
        source_refs=(SourceRef("geoapify", "place-alias"),),
    )
    merged = Venue(
        id="osm:node/alias",
        name="Alias cafe",
        category="cafe",
        category_label="Кофейня",
        latitude=58.01,
        longitude=56.25,
        source="osm",
        source_id="node/alias",
        source_refs=(
            SourceRef("osm", "node/alias"),
            SourceRef("geoapify", "place-alias"),
        ),
    )
    return geo, merged


@pytest.mark.asyncio
async def test_toggle_removes_existing_favorite_through_provider_alias(tmp_path) -> None:
    database_path = tmp_path / "permplaces.db"
    repository = FavoritesRepository(str(database_path))
    await repository.initialize()
    geo, merged = aliased_venues()

    assert await repository.toggle(user_id=80, venue=geo) is True
    assert await repository.toggle(user_id=80, venue=merged) is False

    assert await repository.list_for_user(user_id=80) == []


@pytest.mark.asyncio
async def test_toggle_alias_matching_is_user_scoped(tmp_path) -> None:
    database_path = tmp_path / "permplaces.db"
    repository = FavoritesRepository(str(database_path))
    await repository.initialize()
    geo, merged = aliased_venues()

    assert await repository.toggle(user_id=81, venue=geo) is True
    assert await repository.toggle(user_id=82, venue=merged) is True
    assert await repository.toggle(user_id=81, venue=merged) is False

    user_82 = await repository.list_for_user(user_id=82)
    assert len(user_82) == 1
    assert user_82[0].id == merged.id


@pytest.mark.asyncio
async def test_list_hides_historical_duplicate_provider_aliases(tmp_path) -> None:
    database_path = tmp_path / "permplaces.db"
    repository = FavoritesRepository(str(database_path))
    await repository.initialize()
    geo, merged = aliased_venues()

    with sqlite3.connect(database_path) as database:
        database.executemany(
            """
            INSERT INTO favorites (user_id, venue_id, payload)
            VALUES (?, ?, ?)
            """,
            [
                (
                    83,
                    geo.id,
                    json.dumps(asdict(geo), ensure_ascii=False),
                ),
                (
                    83,
                    merged.id,
                    json.dumps(asdict(merged), ensure_ascii=False),
                ),
            ],
        )
        database.commit()

    favorites = await repository.list_for_user(user_id=83)

    assert len(favorites) == 1


@pytest.mark.asyncio
async def test_different_provider_identities_remain_separate_favorites(tmp_path) -> None:
    database_path = tmp_path / "permplaces.db"
    repository = FavoritesRepository(str(database_path))
    await repository.initialize()

    first = Venue(
        id="osm:node/branch-1",
        name="Chain",
        category="cafe",
        category_label="Кофейня",
        latitude=58.01,
        longitude=56.25,
        source="osm",
        source_id="node/branch-1",
    )
    second = Venue(
        id="osm:node/branch-2",
        name="Chain",
        category="cafe",
        category_label="Кофейня",
        latitude=58.02,
        longitude=56.26,
        source="osm",
        source_id="node/branch-2",
    )

    assert await repository.toggle(user_id=84, venue=first) is True
    assert await repository.toggle(user_id=84, venue=second) is True

    favorites = await repository.list_for_user(user_id=84)
    assert {item.id for item in favorites} == {first.id, second.id}



@pytest.mark.asyncio
async def test_favorite_toggle_maintains_indexed_identity_alias_rows(tmp_path) -> None:
    database_path = tmp_path / "permplaces.db"
    repository = FavoritesRepository(str(database_path))
    await repository.initialize()
    _geo, merged = aliased_venues()

    assert await repository.toggle(user_id=85, venue=merged) is True

    with sqlite3.connect(database_path) as database:
        aliases = database.execute(
            """
            SELECT identity_key
            FROM favorite_identity_aliases
            WHERE user_id = 85
            ORDER BY identity_key
            """
        ).fetchall()

    assert aliases == [
        ("geoapify:place-alias",),
        ("osm:node/alias",),
    ]

    assert await repository.toggle(user_id=85, venue=merged) is False

    with sqlite3.connect(database_path) as database:
        alias_count = database.execute(
            """
            SELECT COUNT(*)
            FROM favorite_identity_aliases
            WHERE user_id = 85
            """
        ).fetchone()

    assert alias_count == (0,)



@pytest.mark.asyncio
async def test_removing_favorite_also_removes_personal_note_across_aliases(
    tmp_path,
) -> None:
    database_path = tmp_path / "permplaces.db"
    favorites = FavoritesRepository(str(database_path))
    notes = NotesRepository(str(database_path))
    await favorites.initialize()

    _geo, merged = aliased_venues()
    assert await favorites.toggle(user_id=86, venue=merged) is True
    await notes.set_note(
        user_id=86,
        venue=merged,
        text="Удалится вместе с избранным",
    )

    assert await favorites.toggle(user_id=86, venue=merged) is False

    with sqlite3.connect(database_path) as database:
        note_count = database.execute(
            """
            SELECT COUNT(*)
            FROM favorite_notes
            WHERE user_id = 86
            """
        ).fetchone()

    assert note_count == (0,)
