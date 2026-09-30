import httpx
import pytest

from app.filters import PlaceFilters
from app.providers.base import ProviderError
from app.providers.geoapify import GeoapifyProvider


@pytest.mark.asyncio
async def test_geoapify_nearby_is_credit_bounded_and_parses_places() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert request.url.params["apiKey"] == "free-key"
        assert request.url.params["categories"] == "catering.cafe"
        assert request.url.params["filter"] == "circle:56.250170,58.010460,3000"
        assert request.url.params["bias"] == "proximity:56.250170,58.010460"
        assert request.url.params["limit"] == "20"
        assert request.url.params["lang"] == "ru"
        assert "conditions" not in request.url.params
        return httpx.Response(
            200,
            json={
                "type": "FeatureCollection",
                "features": [
                    {
                        "type": "Feature",
                        "properties": {
                            "place_id": "place-1",
                            "name": "Тестовая кофейня",
                            "address_line2": "улица Ленина, 10, Пермь",
                            "district": "Ленинский район",
                            "lat": 58.011,
                            "lon": 56.251,
                            "categories": ["catering", "catering.cafe"],
                        },
                        "geometry": {
                            "type": "Point",
                            "coordinates": [56.251, 58.011],
                        },
                    }
                ],
            },
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = GeoapifyProvider(
        api_key="free-key",
        endpoint="https://example.test/v2/places",
        client=client,
    )

    venues = await provider.search_nearby(
        category="cafe",
        latitude=58.01046,
        longitude=56.25017,
        radius_m=3000,
        limit=80,
    )
    await client.aclose()

    assert len(venues) == 1
    assert venues[0].id == "geoapify:place-1"
    assert venues[0].source == "geoapify"
    assert venues[0].source_id == "place-1"
    assert venues[0].address == "улица Ленина, 10, Пермь"
    assert venues[0].district == "Ленинский район"
    assert venues[0].wifi is None


@pytest.mark.asyncio
async def test_geoapify_wifi_filter_uses_condition_and_marks_verified() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["conditions"] == "internet_access"
        return httpx.Response(
            200,
            json={
                "type": "FeatureCollection",
                "features": [
                    {
                        "type": "Feature",
                        "properties": {
                            "place_id": "wifi-1",
                            "name": "Wi-Fi Cafe",
                            "lat": 58.01,
                            "lon": 56.25,
                            "categories": ["catering.cafe"],
                        },
                        "geometry": {
                            "type": "Point",
                            "coordinates": [56.25, 58.01],
                        },
                    }
                ],
            },
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = GeoapifyProvider(api_key="key", endpoint="https://example.test", client=client)

    venues = await provider.search_nearby(
        category="cafe",
        latitude=58.01,
        longitude=56.25,
        radius_m=1000,
        limit=5,
        filters=PlaceFilters(wifi=True),
    )
    await client.aclose()

    assert venues[0].wifi is True


@pytest.mark.asyncio
async def test_geoapify_infers_internet_access_from_returned_categories() -> None:
    client = httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                json={
                    "type": "FeatureCollection",
                    "features": [
                        {
                            "type": "Feature",
                            "properties": {
                                "place_id": "wifi-2",
                                "name": "Connected",
                                "lat": 58.01,
                                "lon": 56.25,
                                "categories": [
                                    "catering.cafe",
                                    "internet_access.free",
                                ],
                            },
                        }
                    ],
                },
            )
        )
    )
    provider = GeoapifyProvider(api_key="key", endpoint="https://example.test", client=client)

    venues = await provider.search_nearby(
        category="cafe",
        latitude=58.01,
        longitude=56.25,
        radius_m=1000,
        limit=5,
    )
    await client.aclose()

    assert venues[0].wifi is True


@pytest.mark.asyncio
async def test_geoapify_does_not_fake_unsupported_filters_or_breakfast() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError(f"unexpected network request: {request.url}")

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = GeoapifyProvider(api_key="key", endpoint="https://example.test", client=client)

    unsupported_filters = (
        PlaceFilters(outdoor_seating=True),
        PlaceFilters(open_now=True),
        PlaceFilters(family_friendly=True),
        PlaceFilters(open_late=True),
    )
    for filters in unsupported_filters:
        assert (
            await provider.search_nearby(
                category="cafe",
                latitude=58.01,
                longitude=56.25,
                radius_m=1000,
                limit=5,
                filters=filters,
            )
            == []
        )

    assert (
        await provider.search_nearby(
            category="breakfast",
            latitude=58.01,
            longitude=56.25,
            radius_m=1000,
            limit=5,
        )
        == []
    )
    await client.aclose()


@pytest.mark.asyncio
async def test_geoapify_district_search_stays_osm_authoritative() -> None:
    client = httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda request: (_ for _ in ()).throw(
                AssertionError(f"unexpected network request: {request.url}")
            )
        )
    )
    provider = GeoapifyProvider(api_key="key", endpoint="https://example.test", client=client)

    venues = await provider.search_in_area(
        category="cafe",
        relation_id=1_268_697,
        limit=5,
    )
    await client.aclose()

    assert venues == []


@pytest.mark.asyncio
async def test_geoapify_http_failure_is_provider_error() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"message": "quota"})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = GeoapifyProvider(api_key="key", endpoint="https://example.test", client=client)

    with pytest.raises(ProviderError, match="temporarily unavailable"):
        await provider.search_nearby(
            category="restaurant",
            latitude=58.01,
            longitude=56.25,
            radius_m=1000,
            limit=5,
        )
    await client.aclose()


@pytest.mark.asyncio
async def test_geoapify_malformed_payload_is_provider_error() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"features": []})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = GeoapifyProvider(api_key="key", endpoint="https://example.test", client=client)

    with pytest.raises(ProviderError, match="unexpected response"):
        await provider.search_nearby(
            category="restaurant",
            latitude=58.01,
            longitude=56.25,
            radius_m=1000,
            limit=5,
        )
    await client.aclose()


def test_geoapify_requires_explicit_api_key() -> None:
    with pytest.raises(ValueError, match="must not be empty"):
        GeoapifyProvider(api_key="   ")
