import httpx
import pytest

from app.providers.overpass import OverpassProvider, build_overpass_query


def test_build_query_uses_radius_location_and_category() -> None:
    query = build_overpass_query(
        category="cafe",
        latitude=58.01046,
        longitude=56.25017,
        radius_m=1500,
    )

    assert "around:1500,58.010460,56.250170" in query
    assert '["amenity"="cafe"]' in query
    assert "out center tags;" in query


@pytest.mark.asyncio
async def test_provider_parses_node_and_way_center() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        return httpx.Response(
            200,
            json={
                "elements": [
                    {
                        "type": "node",
                        "id": 101,
                        "lat": 58.01,
                        "lon": 56.25,
                        "tags": {
                            "name": "Coffee One",
                            "amenity": "cafe",
                            "addr:street": "Ленина",
                            "addr:housenumber": "10",
                            "opening_hours": "Mo-Su 08:00-22:00",
                            "cuisine": "coffee_shop;breakfast",
                        },
                    },
                    {
                        "type": "way",
                        "id": 202,
                        "center": {"lat": 58.011, "lon": 56.251},
                        "tags": {"name": "Coffee Two", "amenity": "cafe"},
                    },
                ]
            },
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = OverpassProvider(endpoint="https://example.test/api", client=client)

    venues = await provider.search_nearby(
        category="cafe",
        latitude=58.01046,
        longitude=56.25017,
        radius_m=3000,
        limit=10,
    )

    await client.aclose()

    assert [venue.name for venue in venues] == ["Coffee One", "Coffee Two"]
    assert venues[0].address == "Ленина, 10"
    assert venues[0].source == "osm"
    assert venues[0].source_id == "node/101"
    assert venues[0].cuisine == ("coffee_shop", "breakfast")
    assert venues[1].source_url.endswith("/way/202")
