from datetime import datetime
from zoneinfo import ZoneInfo

import httpx
import pytest

from app.filters import PlaceFilters
from app.providers.base import ProviderError
from app.providers.foursquare import FoursquareProvider, late_open_at


@pytest.mark.asyncio
async def test_foursquare_request_and_parse_rich_fields() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == "Bearer service-secret"
        assert request.headers["X-Places-Api-Version"] == "2025-06-17"
        params = request.url.params
        assert params["query"] == "coffee"
        assert params["ll"] == "58.010460,56.250170"
        assert params["radius"] == "3000"
        assert params["limit"] == "25"
        assert params["sort"] == "DISTANCE"
        assert "rating" in params["fields"]
        assert "stats" in params["fields"]
        return httpx.Response(
            200,
            json={
                "results": [
                    {
                        "fsq_place_id": "fsq-1",
                        "name": "Тестовая кофейня",
                        "latitude": 58.011,
                        "longitude": 56.251,
                        "location": {
                            "formatted_address": "ул. Ленина, 10, Пермь",
                        },
                        "tel": "+7 342 200-00-00",
                        "website": "https://example.test",
                        "rating": 8.7,
                        "price": 2,
                        "stats": {"total_ratings": 321},
                        "attributes": {
                            "outdoor_seating": True,
                            "wifi": "Free",
                        },
                        "hours": {
                            "display": "09:00–23:00",
                            "open_now": True,
                        },
                    }
                ]
            },
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = FoursquareProvider(
        api_key="service-secret",
        endpoint="https://example.test/places/search",
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
    venue = venues[0]
    assert venue.id == "foursquare:fsq-1"
    assert venue.source == "foursquare"
    assert venue.address == "ул. Ленина, 10, Пермь"
    assert venue.rating == 8.7
    assert venue.rating_scale == 10.0
    assert venue.review_count == 321
    assert venue.price_label == "₽₽"
    assert venue.outdoor_seating is True
    assert venue.wifi is True
    assert venue.is_open_now is True


@pytest.mark.asyncio
async def test_foursquare_open_now_uses_provider_filter() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["open_now"] == "true"
        return httpx.Response(
            200,
            json={
                "results": [
                    {
                        "fsq_place_id": "fsq-open",
                        "name": "Open",
                        "latitude": 58.01,
                        "longitude": 56.25,
                    }
                ]
            },
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = FoursquareProvider(
        api_key="key",
        endpoint="https://example.test",
        client=client,
    )

    venues = await provider.search_nearby(
        category="restaurant",
        latitude=58.01,
        longitude=56.25,
        radius_m=1000,
        limit=5,
        filters=PlaceFilters(open_now=True),
    )
    await client.aclose()

    assert venues[0].is_open_now is True


def test_late_open_at_uses_perm_local_weekday() -> None:
    moment = datetime(2026, 9, 29, 20, 0, tzinfo=ZoneInfo("Asia/Yekaterinburg"))

    assert late_open_at(moment) == "2T2300"


@pytest.mark.asyncio
async def test_foursquare_late_filter_uses_open_at() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["open_at"].endswith("T2300")
        return httpx.Response(
            200,
            json={
                "results": [
                    {
                        "fsq_place_id": "fsq-late",
                        "name": "Late",
                        "latitude": 58.01,
                        "longitude": 56.25,
                    }
                ]
            },
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = FoursquareProvider(
        api_key="key",
        endpoint="https://example.test",
        client=client,
    )

    venues = await provider.search_nearby(
        category="bar",
        latitude=58.01,
        longitude=56.25,
        radius_m=1000,
        limit=5,
        filters=PlaceFilters(open_late=True),
    )
    await client.aclose()

    assert venues[0].is_open_late is True


@pytest.mark.asyncio
async def test_foursquare_unsupported_semantics_fail_closed() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError(f"unexpected network request: {request.url}")

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = FoursquareProvider(
        api_key="key",
        endpoint="https://example.test",
        client=client,
    )

    family = await provider.search_nearby(
        category="restaurant",
        latitude=58.01,
        longitude=56.25,
        radius_m=1000,
        limit=5,
        filters=PlaceFilters(family_friendly=True),
    )
    combined_time = await provider.search_nearby(
        category="bar",
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

    assert family == []
    assert combined_time == []
    assert surprise == []


@pytest.mark.asyncio
async def test_foursquare_requires_confirmed_wifi_and_terrace_for_filters() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "results": [
                    {
                        "fsq_place_id": "good",
                        "name": "Confirmed",
                        "latitude": 58.01,
                        "longitude": 56.25,
                        "attributes": {
                            "outdoor_seating": True,
                            "wifi": "Paid",
                        },
                    },
                    {
                        "fsq_place_id": "unknown",
                        "name": "Unknown",
                        "latitude": 58.011,
                        "longitude": 56.251,
                        "attributes": {},
                    },
                ]
            },
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = FoursquareProvider(
        api_key="key",
        endpoint="https://example.test",
        client=client,
    )

    venues = await provider.search_nearby(
        category="cafe",
        latitude=58.01,
        longitude=56.25,
        radius_m=1000,
        limit=5,
        filters=PlaceFilters(wifi=True, outdoor_seating=True),
    )
    await client.aclose()

    assert [venue.id for venue in venues] == ["foursquare:good"]


@pytest.mark.asyncio
async def test_foursquare_malformed_response_is_provider_error() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"unexpected": []})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = FoursquareProvider(
        api_key="key",
        endpoint="https://example.test",
        client=client,
    )

    with pytest.raises(ProviderError, match="unexpected response"):
        await provider.search_nearby(
            category="cafe",
            latitude=58.01,
            longitude=56.25,
            radius_m=1000,
            limit=5,
        )
    await client.aclose()


def test_foursquare_requires_explicit_api_key() -> None:
    with pytest.raises(ValueError, match="must not be empty"):
        FoursquareProvider(api_key="   ")
