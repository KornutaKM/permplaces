import asyncio

import pytest

from app.data import Venue
from app.filters import PlaceFilters
from app.providers.cache import CachedPlacesProvider


class FakeProvider:
    def __init__(self) -> None:
        self.nearby_calls = 0
        self.area_calls = 0
        self.release = asyncio.Event()
        self.started = asyncio.Event()
        self.block = False

    async def search_nearby(
        self,
        *,
        category: str,
        latitude: float,
        longitude: float,
        radius_m: int,
        limit: int,
        filters: PlaceFilters | None = None,
    ) -> list[Venue]:
        del category, latitude, longitude, radius_m, limit, filters
        self.nearby_calls += 1
        self.started.set()
        if self.block:
            await self.release.wait()
        return [
            Venue(
                id="osm:node/1",
                name="Cached Cafe",
                category="cafe",
                category_label="Кофейня",
                latitude=58.01,
                longitude=56.25,
                source="osm",
                source_id="node/1",
            )
        ]

    async def search_in_area(
        self,
        *,
        category: str,
        relation_id: int,
        limit: int,
        filters: PlaceFilters | None = None,
    ) -> list[Venue]:
        del category, relation_id, limit, filters
        self.area_calls += 1
        return [
            Venue(
                id="osm:node/2",
                name="Area Cafe",
                category="cafe",
                category_label="Кофейня",
                latitude=58.02,
                longitude=56.26,
                source="osm",
                source_id="node/2",
            )
        ]


@pytest.mark.asyncio
async def test_cache_hit_avoids_second_upstream_call() -> None:
    provider = FakeProvider()
    cache = CachedPlacesProvider(provider, ttl_seconds=120)

    first = await cache.search_nearby(
        category="cafe",
        latitude=58.01,
        longitude=56.25,
        radius_m=3000,
        limit=5,
    )
    second = await cache.search_nearby(
        category="cafe",
        latitude=58.01,
        longitude=56.25,
        radius_m=3000,
        limit=5,
    )

    assert provider.nearby_calls == 1
    assert first == second
    assert first is not second


@pytest.mark.asyncio
async def test_cache_key_includes_filters() -> None:
    provider = FakeProvider()
    cache = CachedPlacesProvider(provider, ttl_seconds=120)

    await cache.search_nearby(
        category="cafe",
        latitude=58.01,
        longitude=56.25,
        radius_m=3000,
        limit=5,
        filters=PlaceFilters(wifi=True),
    )
    await cache.search_nearby(
        category="cafe",
        latitude=58.01,
        longitude=56.25,
        radius_m=3000,
        limit=5,
        filters=PlaceFilters(outdoor_seating=True),
    )

    assert provider.nearby_calls == 2


@pytest.mark.asyncio
async def test_expired_entry_is_refetched() -> None:
    now = [100.0]
    provider = FakeProvider()
    cache = CachedPlacesProvider(
        provider,
        ttl_seconds=10,
        clock=lambda: now[0],
    )

    await cache.search_in_area(
        category="cafe",
        relation_id=1_268_697,
        limit=5,
    )
    now[0] = 109.9
    await cache.search_in_area(
        category="cafe",
        relation_id=1_268_697,
        limit=5,
    )
    now[0] = 110.0
    await cache.search_in_area(
        category="cafe",
        relation_id=1_268_697,
        limit=5,
    )

    assert provider.area_calls == 2


@pytest.mark.asyncio
async def test_identical_concurrent_misses_are_coalesced() -> None:
    provider = FakeProvider()
    provider.block = True
    cache = CachedPlacesProvider(provider, ttl_seconds=120)

    first = asyncio.create_task(
        cache.search_nearby(
            category="cafe",
            latitude=58.01,
            longitude=56.25,
            radius_m=3000,
            limit=5,
        )
    )
    second = asyncio.create_task(
        cache.search_nearby(
            category="cafe",
            latitude=58.01,
            longitude=56.25,
            radius_m=3000,
            limit=5,
        )
    )

    await asyncio.wait_for(provider.started.wait(), timeout=1)
    await asyncio.sleep(0)
    assert provider.nearby_calls == 1

    provider.release.set()
    await asyncio.gather(first, second)

    assert provider.nearby_calls == 1


@pytest.mark.asyncio
async def test_lru_eviction_keeps_cache_bounded() -> None:
    provider = FakeProvider()
    cache = CachedPlacesProvider(provider, ttl_seconds=120, max_entries=1)

    await cache.search_nearby(
        category="cafe",
        latitude=58.01,
        longitude=56.25,
        radius_m=1000,
        limit=5,
    )
    await cache.search_nearby(
        category="cafe",
        latitude=58.01,
        longitude=56.25,
        radius_m=2000,
        limit=5,
    )
    await cache.search_nearby(
        category="cafe",
        latitude=58.01,
        longitude=56.25,
        radius_m=1000,
        limit=5,
    )

    assert provider.nearby_calls == 3


def test_cache_rejects_invalid_bounds() -> None:
    provider = FakeProvider()

    with pytest.raises(ValueError):
        CachedPlacesProvider(provider, ttl_seconds=-1)

    with pytest.raises(ValueError):
        CachedPlacesProvider(provider, max_entries=0)
