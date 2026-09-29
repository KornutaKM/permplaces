import httpx
import pytest

from app.filters import PlaceFilters
from app.providers.base import ProviderError
from app.providers.twogis import TwoGISProvider


@pytest.mark.asyncio
async def test_twogis_nearby_request_and_parse() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        params = request.url.params
        assert params["key"] == "demo-secret"
        assert params["q"] == "кафе"
        assert params["type"] == "branch"
        assert params["point"] == "56.250170,58.010460"
        assert params["radius"] == "3000"
        assert params["page_size"] == "10"
        assert params["fields"] == "items.point"
        assert params["search_nearby"] == "true"
        return httpx.Response(
            200,
            json={
                "meta": {"code": 200},
                "result": {
                    "items": [
                        {
                            "id": "70000001000000001",
                            "name": "Тестовая кофейня",
                            "type": "branch",
                            "address_name": "улица Ленина, 10",
                            "point": {"lat": 58.011, "lon": 56.251},
                        },
                        {
                            "id": "building-1",
                            "name": "Не организация",
                            "type": "building",
                            "point": {"lat": 58.012, "lon": 56.252},
                        },
                    ]
                },
            },
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = TwoGISProvider(
        api_key="demo-secret",
        endpoint="https://example.test/3.0/items",
        client=client,
    )

    venues = await provider.search_nearby(
        category="cafe",
        latitude=58.01046,
        longitude=56.25017,
        radius_m=3000,
        limit=25,
    )
    await client.aclose()

    assert len(venues) == 1
    assert venues[0].id == "2gis:70000001000000001"
    assert venues[0].source == "2gis"
    assert venues[0].address == "улица Ленина, 10"
    assert venues[0].latitude == 58.011
    assert venues[0].longitude == 56.251


@pytest.mark.asyncio
async def test_twogis_open_now_uses_provider_work_time() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["work_time"] == "now"
        return httpx.Response(
            200,
            json={
                "meta": {"code": 200},
                "result": {
                    "items": [
                        {
                            "id": "1",
                            "name": "Open",
                            "type": "branch",
                            "point": {"lat": 58.01, "lon": 56.25},
                        }
                    ]
                },
            },
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = TwoGISProvider(api_key="key", endpoint="https://example.test", client=client)

    venues = await provider.search_nearby(
        category="cafe",
        latitude=58.01,
        longitude=56.25,
        radius_m=1000,
        limit=5,
        filters=PlaceFilters(open_now=True),
    )
    await client.aclose()

    assert venues[0].is_open_now is True


@pytest.mark.asyncio
async def test_twogis_late_filter_uses_23_00_work_time() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["work_time"] == "today,23:00"
        return httpx.Response(
            200,
            json={
                "meta": {"code": 200},
                "result": {
                    "items": [
                        {
                            "id": "2",
                            "name": "Late",
                            "type": "branch",
                            "point": {"lat": 58.01, "lon": 56.25},
                        }
                    ]
                },
            },
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = TwoGISProvider(api_key="key", endpoint="https://example.test", client=client)

    venues = await provider.search_nearby(
        category="restaurant",
        latitude=58.01,
        longitude=56.25,
        radius_m=1000,
        limit=5,
        filters=PlaceFilters(open_late=True),
    )
    await client.aclose()

    assert venues[0].is_open_late is True


@pytest.mark.asyncio
async def test_twogis_does_not_fake_unsupported_filters() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError(f"unexpected network request: {request.url}")

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = TwoGISProvider(api_key="key", endpoint="https://example.test", client=client)

    venues = await provider.search_nearby(
        category="cafe",
        latitude=58.01,
        longitude=56.25,
        radius_m=1000,
        limit=5,
        filters=PlaceFilters(wifi=True),
    )
    combined = await provider.search_nearby(
        category="cafe",
        latitude=58.01,
        longitude=56.25,
        radius_m=1000,
        limit=5,
        filters=PlaceFilters(open_now=True, open_late=True),
    )
    surprise = await provider.search_nearby(
        category="food_drink",
        latitude=58.01,
        longitude=56.25,
        radius_m=1000,
        limit=5,
    )
    await client.aclose()

    assert venues == []
    assert combined == []
    assert surprise == []


@pytest.mark.asyncio
async def test_twogis_district_search_stays_osm_authoritative() -> None:
    client = httpx.AsyncClient(transport=httpx.MockTransport(lambda request: None))
    provider = TwoGISProvider(api_key="key", endpoint="https://example.test", client=client)

    venues = await provider.search_in_area(
        category="cafe",
        relation_id=1_268_697,
        limit=5,
    )
    await client.aclose()

    assert venues == []


@pytest.mark.asyncio
async def test_twogis_meta_error_is_provider_error() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"meta": {"code": 403}, "result": {}},
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = TwoGISProvider(api_key="key", endpoint="https://example.test", client=client)

    with pytest.raises(ProviderError, match="unsuccessful"):
        await provider.search_nearby(
            category="cafe",
            latitude=58.01,
            longitude=56.25,
            radius_m=1000,
            limit=5,
        )
    await client.aclose()


def test_twogis_requires_explicit_api_key() -> None:
    with pytest.raises(ValueError, match="must not be empty"):
        TwoGISProvider(api_key="   ")
