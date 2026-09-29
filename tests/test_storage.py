import pytest

from app.data import Venue
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
