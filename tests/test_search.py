import pytest

from app.data import Venue
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
    ) -> list[Venue]:
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
