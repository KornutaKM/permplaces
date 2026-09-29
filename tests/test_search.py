import pytest

from app.data import Venue
from app.filters import PlaceFilters
from app.search import SearchService, distance_m


class FakeProvider:
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
        self.nearby_filters = filters
        del category, latitude, longitude, radius_m, limit
        return [
            Venue(
                id="far",
                name="Far",
                category="cafe",
                category_label="Кофейня",
                latitude=58.03,
                longitude=56.25,
                source="osm",
                source_id="node/2",
            ),
            Venue(
                id="near",
                name="Near",
                category="cafe",
                category_label="Кофейня",
                latitude=58.011,
                longitude=56.25,
                source="osm",
                source_id="node/1",
            ),
        ]

    async def search_in_area(
        self,
        *,
        category: str,
        relation_id: int,
        limit: int,
        filters: PlaceFilters | None = None,
    ) -> list[Venue]:
        self.area_filters = filters
        del category, relation_id, limit
        return [
            Venue(
                id="z",
                name="Zulu",
                category="cafe",
                category_label="Кофейня",
                latitude=58.01,
                longitude=56.25,
                source="osm",
                source_id="node/9",
                distance_m=999,
            ),
            Venue(
                id="a",
                name="Alpha",
                category="cafe",
                category_label="Кофейня",
                latitude=58.02,
                longitude=56.26,
                source="osm",
                source_id="node/8",
                distance_m=888,
            ),
        ]


def test_distance_is_zero_for_same_point() -> None:
    assert distance_m(58.01046, 56.25017, 58.01046, 56.25017) == 0


@pytest.mark.asyncio
async def test_search_sorts_by_distance() -> None:
    service = SearchService(FakeProvider())

    venues = await service.nearby(
        category="cafe",
        latitude=58.01046,
        longitude=56.25017,
        radius_m=5000,
        limit=5,
    )

    assert [venue.id for venue in venues] == ["near", "far"]
    assert venues[0].distance_m is not None
    assert venues[0].distance_m < venues[1].distance_m


@pytest.mark.asyncio
async def test_district_search_sorts_by_name_and_clears_distance() -> None:
    service = SearchService(FakeProvider())

    venues = await service.in_district(
        category="cafe",
        relation_id=1_268_696,
        district_name="Дзержинский",
        limit=5,
    )

    assert [venue.id for venue in venues] == ["a", "z"]
    assert all(venue.district == "Дзержинский" for venue in venues)
    assert all(venue.distance_m is None for venue in venues)


@pytest.mark.asyncio
async def test_search_passes_filters_to_nearby_provider() -> None:
    provider = FakeProvider()
    service = SearchService(provider)
    filters = PlaceFilters(outdoor_seating=True, wifi=True)

    await service.nearby(
        category="cafe",
        latitude=58.01046,
        longitude=56.25017,
        radius_m=5000,
        limit=5,
        filters=filters,
    )

    assert provider.nearby_filters == filters


@pytest.mark.asyncio
async def test_search_passes_filters_to_area_provider() -> None:
    provider = FakeProvider()
    service = SearchService(provider)
    filters = PlaceFilters(wifi=True)

    await service.in_district(
        category="cafe",
        relation_id=1_268_696,
        district_name="Дзержинский",
        limit=5,
        filters=filters,
    )

    assert provider.area_filters == filters



class OpenNowProvider:
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
        return [
            Venue(
                id="open",
                name="Open",
                category="cafe",
                category_label="Кофейня",
                latitude=58.0105,
                longitude=56.2502,
                source="osm",
                source_id="node/100",
                opening_hours="24/7",
            ),
            Venue(
                id="closed",
                name="Closed",
                category="cafe",
                category_label="Кофейня",
                latitude=58.011,
                longitude=56.251,
                source="osm",
                source_id="node/101",
                opening_hours="24/7 off",
            ),
            Venue(
                id="unknown",
                name="Unknown",
                category="cafe",
                category_label="Кофейня",
                latitude=58.012,
                longitude=56.252,
                source="osm",
                source_id="node/102",
                opening_hours="definitely invalid",
            ),
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
        return await self.search_nearby(
            category="cafe",
            latitude=58.01,
            longitude=56.25,
            radius_m=3000,
            limit=10,
        )


@pytest.mark.asyncio
async def test_open_now_filter_is_fail_closed() -> None:
    service = SearchService(OpenNowProvider())

    venues = await service.nearby(
        category="cafe",
        latitude=58.01046,
        longitude=56.25017,
        radius_m=5000,
        limit=5,
        filters=PlaceFilters(open_now=True),
    )

    assert [venue.id for venue in venues] == ["open"]
    assert venues[0].is_open_now is True
