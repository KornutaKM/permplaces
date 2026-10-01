import pytest

from app.data import Venue
from app.filters import PlaceFilters
from app.providers.base import ProviderError
from app.providers.capabilities import ProviderCapabilities
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



class CapabilityProvider(FakeProvider):
    def __init__(
        self,
        *,
        capabilities: ProviderCapabilities,
        result: list[Venue] | None = None,
    ) -> None:
        super().__init__(result=result)
        self.capabilities = capabilities
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
        self.nearby_calls += 1
        return await super().search_nearby(
            category=category,
            latitude=latitude,
            longitude=longitude,
            radius_m=radius_m,
            limit=limit,
            filters=filters,
        )

    async def search_in_area(
        self,
        *,
        category: str,
        relation_id: int,
        limit: int,
        filters: PlaceFilters | None = None,
    ) -> list[Venue]:
        self.area_calls += 1
        return await super().search_in_area(
            category=category,
            relation_id=relation_id,
            limit=limit,
            filters=filters,
        )


@pytest.mark.asyncio
async def test_composite_skips_provider_without_district_capability() -> None:
    area_provider = CapabilityProvider(
        capabilities=ProviderCapabilities(
            categories=frozenset({"cafe"}),
            nearby_search=True,
            district_search=True,
        ),
        result=[item("osm", "node/area")],
    )
    nearby_only = CapabilityProvider(
        capabilities=ProviderCapabilities(
            categories=frozenset({"cafe"}),
            nearby_search=True,
        ),
        result=[item("geoapify", "place/area")],
    )
    provider = CompositePlacesProvider([area_provider, nearby_only])

    results = await provider.search_in_area(
        category="cafe",
        relation_id=1_268_697,
        limit=5,
    )

    assert [result.id for result in results] == ["osm:node/area"]
    assert area_provider.area_calls == 1
    assert nearby_only.area_calls == 0


@pytest.mark.asyncio
async def test_composite_skips_provider_that_cannot_prove_active_filter() -> None:
    without_wifi = CapabilityProvider(
        capabilities=ProviderCapabilities(
            categories=frozenset({"cafe"}),
            nearby_search=True,
        ),
        result=[item("catalog", "no-wifi")],
    )
    with_wifi = CapabilityProvider(
        capabilities=ProviderCapabilities(
            categories=frozenset({"cafe"}),
            nearby_search=True,
            wifi=True,
        ),
        result=[item("catalog", "wifi")],
    )
    provider = CompositePlacesProvider([without_wifi, with_wifi])

    results = await provider.search_nearby(
        category="cafe",
        latitude=58.01,
        longitude=56.25,
        radius_m=3000,
        limit=5,
        filters=PlaceFilters(wifi=True),
    )

    assert [result.id for result in results] == ["catalog:wifi"]
    assert without_wifi.nearby_calls == 0
    assert with_wifi.nearby_calls == 1


@pytest.mark.asyncio
async def test_composite_returns_empty_when_no_provider_supports_query() -> None:
    unsupported = CapabilityProvider(
        capabilities=ProviderCapabilities(
            categories=frozenset({"restaurant"}),
            nearby_search=True,
        ),
        result=[item("catalog", "wrong-category")],
    )
    provider = CompositePlacesProvider([unsupported])

    results = await provider.search_nearby(
        category="cafe",
        latitude=58.01,
        longitude=56.25,
        radius_m=3000,
        limit=5,
    )

    assert results == []
    assert unsupported.nearby_calls == 0
