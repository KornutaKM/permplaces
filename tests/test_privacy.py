import sqlite3

import pytest

from app.data import Venue
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
    repository = UserDataRepository(path)
    await repository.initialize()

    await favorites.toggle(user_id=10, venue=venue("node/1"))
    await favorites.toggle(user_id=11, venue=venue("node/2"))
    await ratings.set_rating(user_id=10, venue=venue("node/1"), score=5)
    await ratings.set_rating(user_id=10, venue=venue("node/3"), score=4)
    await ratings.set_rating(user_id=11, venue=venue("node/2"), score=1)

    summary = await repository.summary_for_user(user_id=10)

    assert summary.favorites == 1
    assert summary.ratings == 2
    assert summary.total_rows == 3


@pytest.mark.asyncio
async def test_user_data_delete_is_atomic_and_user_scoped(tmp_path) -> None:
    path = str(tmp_path / "permplaces.db")
    favorites = FavoritesRepository(path)
    ratings = RatingsRepository(path)
    repository = UserDataRepository(path)
    await repository.initialize()

    await favorites.toggle(user_id=20, venue=venue("node/20"))
    await favorites.toggle(user_id=21, venue=venue("node/21"))
    await ratings.set_rating(user_id=20, venue=venue("node/20"), score=5)
    await ratings.set_rating(user_id=21, venue=venue("node/21"), score=3)

    deleted = await repository.delete_for_user(user_id=20)

    assert deleted.favorites == 1
    assert deleted.ratings == 1
    assert await repository.summary_for_user(user_id=20) == deleted.__class__(0, 0)

    other = await repository.summary_for_user(user_id=21)
    assert other.favorites == 1
    assert other.ratings == 1

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
