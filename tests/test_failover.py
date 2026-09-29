import pytest

from app.data import Venue
from app.filters import PlaceFilters
from app.providers.base import ProviderError
from app.providers.failover import FailoverPlacesProvider


def venue(name: str) -> Venue:
    return Venue(
        id=f"osm:node/{name}",
        name=name,
        category="cafe",
        category_label="Кофейня",
        latitude=58.01,
        longitude=56.25,
        source="osm",
        source_id=f"node/{name}",
    )


class FakeProvider:
    def __init__(self, *, result: list[Venue] | None = None, fail: bool = False) -> None:
        self.result = result or []
        self.fail = fail
        self.nearby_calls = 0
        self.area_calls = 0

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
        if self.fail:
            raise ProviderError("provider unavailable")
        return self.result

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
        if self.fail:
            raise ProviderError("provider unavailable")
        return self.result


@pytest.mark.asyncio
async def test_primary_success_does_not_touch_fallback() -> None:
    primary = FakeProvider(result=[venue("primary")])
    fallback = FakeProvider(result=[venue("fallback")])
    provider = FailoverPlacesProvider([primary, fallback])

    result = await provider.search_nearby(
        category="cafe",
        latitude=58.01,
        longitude=56.25,
        radius_m=3000,
        limit=5,
    )

    assert [item.name for item in result] == ["primary"]
    assert primary.nearby_calls == 1
    assert fallback.nearby_calls == 0


@pytest.mark.asyncio
async def test_fallback_is_used_after_provider_error() -> None:
    primary = FakeProvider(fail=True)
    fallback = FakeProvider(result=[venue("fallback")])
    provider = FailoverPlacesProvider([primary, fallback])

    result = await provider.search_in_area(
        category="cafe",
        relation_id=1_268_697,
        limit=5,
    )

    assert [item.name for item in result] == ["fallback"]
    assert primary.area_calls == 1
    assert fallback.area_calls == 1


@pytest.mark.asyncio
async def test_empty_success_does_not_fall_through() -> None:
    primary = FakeProvider(result=[])
    fallback = FakeProvider(result=[venue("fallback")])
    provider = FailoverPlacesProvider([primary, fallback])

    result = await provider.search_nearby(
        category="cafe",
        latitude=58.01,
        longitude=56.25,
        radius_m=3000,
        limit=5,
    )

    assert result == []
    assert fallback.nearby_calls == 0


@pytest.mark.asyncio
async def test_all_failures_raise_provider_error() -> None:
    provider = FailoverPlacesProvider(
        [FakeProvider(fail=True), FakeProvider(fail=True)]
    )

    with pytest.raises(ProviderError, match="all configured places providers failed"):
        await provider.search_nearby(
            category="cafe",
            latitude=58.01,
            longitude=56.25,
            radius_m=3000,
            limit=5,
        )


def test_failover_requires_provider() -> None:
    with pytest.raises(ValueError, match="at least one provider"):
        FailoverPlacesProvider([])
