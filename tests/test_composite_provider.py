import pytest

from app.data import Venue
from app.filters import PlaceFilters
from app.providers.base import ProviderError
from app.providers.composite import CompositePlacesProvider


class FakeProvider:
    def __init__(
        self,
        *,
        result: list[Venue] | None = None,
        error: Exception | None = None,
    ) -> None:
        self.result = result or []
        self.error = error

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
        if self.error:
            raise self.error
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
        if self.error:
            raise self.error
        return self.result


def item(source: str, source_id: str, name: str = "Кофейня") -> Venue:
    return Venue(
        id=f"{source}:{source_id}",
        name=name,
        category="cafe",
        category_label="Кофейня",
        latitude=58.01,
        longitude=56.25,
        source=source,
        source_id=source_id,
    )


@pytest.mark.asyncio
async def test_composite_merges_duplicate_results_in_provider_order() -> None:
    first = FakeProvider(result=[item("osm", "node/1")])
    second = FakeProvider(result=[item("catalog", "42")])
    provider = CompositePlacesProvider([first, second])

    results = await provider.search_nearby(
        category="cafe",
        latitude=58.01,
        longitude=56.25,
        radius_m=3000,
        limit=5,
    )

    assert len(results) == 1
    assert results[0].source == "osm"
    assert len(results[0].source_refs) == 2


@pytest.mark.asyncio
async def test_composite_continues_after_provider_level_failure() -> None:
    failing = FakeProvider(error=ProviderError("unavailable"))
    healthy = FakeProvider(result=[item("catalog", "42")])
    provider = CompositePlacesProvider([failing, healthy])

    results = await provider.search_in_area(
        category="cafe",
        relation_id=1_268_697,
        limit=5,
    )

    assert [result.id for result in results] == ["catalog:42"]


@pytest.mark.asyncio
async def test_composite_fails_when_all_providers_fail() -> None:
    provider = CompositePlacesProvider(
        [
            FakeProvider(error=ProviderError("first")),
            FakeProvider(error=ProviderError("second")),
        ]
    )

    with pytest.raises(ProviderError, match="all configured aggregate providers failed"):
        await provider.search_nearby(
            category="cafe",
            latitude=58.01,
            longitude=56.25,
            radius_m=3000,
            limit=5,
        )


@pytest.mark.asyncio
async def test_composite_does_not_hide_programming_errors() -> None:
    provider = CompositePlacesProvider(
        [
            FakeProvider(error=ValueError("bug")),
            FakeProvider(result=[item("catalog", "42")]),
        ]
    )

    with pytest.raises(ValueError, match="bug"):
        await provider.search_nearby(
            category="cafe",
            latitude=58.01,
            longitude=56.25,
            radius_m=3000,
            limit=5,
        )


def test_composite_requires_at_least_one_provider() -> None:
    with pytest.raises(ValueError, match="at least one provider"):
        CompositePlacesProvider([])
