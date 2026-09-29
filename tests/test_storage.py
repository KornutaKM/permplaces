import asyncio

import pytest

from app.data import FieldSource, SourceRef, Venue
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
    )

    repository = FavoritesRepository(str(database_path))
    await repository.initialize()
    assert await repository.toggle(user_id=50, venue=venue) is True

    restored = (await repository.list_for_user(user_id=50))[0]

    assert restored.source_refs == venue.source_refs
    assert restored.field_sources == venue.field_sources
    assert restored.rating == 4.8
    assert restored.review_count == 150
