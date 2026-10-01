from __future__ import annotations

import logging
from collections.abc import Mapping
from time import monotonic
from typing import Any

import httpx

from app.data import Venue
from app.filters import PlaceFilters
from app.observability import endpoint_label
from app.providers.base import ProviderError
from app.providers.capabilities import GEOAPIFY_CAPABILITIES

logger = logging.getLogger(__name__)

_CATEGORY_QUERIES = {
    "restaurant": "catering.restaurant",
    "cafe": "catering.cafe",
    "bar": "catering.bar,catering.pub",
    "fastfood": "catering.fast_food",
    "pizza": "catering.restaurant.pizza,catering.fast_food.pizza",
    "sushi": "catering.restaurant.sushi",
    "dessert": (
        "catering.cafe.dessert,catering.cafe.cake,"
        "catering.cafe.ice_cream,catering.ice_cream"
    ),
    "food_drink": "catering",
}

_CATEGORY_NAMES = {
    "restaurant": "Ресторан",
    "cafe": "Кофейня",
    "bar": "Бар",
    "fastfood": "Фастфуд",
    "pizza": "Пицца",
    "sushi": "Суши",
    "dessert": "Десерты",
    "food_drink": "Заведение",
}

_MAX_RESULTS_PER_REQUEST = 20


def _supports_filters(filters: PlaceFilters | None) -> bool:
    if filters is None:
        return True
    return not (
        filters.outdoor_seating
        or filters.open_now
        or filters.family_friendly
        or filters.open_late
    )


def _clean_text(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = value.strip()
    return cleaned or None


def _number(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _coordinates(
    feature: Mapping[str, Any],
    properties: Mapping[str, Any],
) -> tuple[float, float] | None:
    lat = _number(properties.get("lat"))
    lon = _number(properties.get("lon"))
    if lat is not None and lon is not None:
        return lat, lon

    geometry = feature.get("geometry")
    if not isinstance(geometry, Mapping) or geometry.get("type") != "Point":
        return None
    coordinates = geometry.get("coordinates")
    if not isinstance(coordinates, list) or len(coordinates) < 2:
        return None
    lon = _number(coordinates[0])
    lat = _number(coordinates[1])
    if lat is None or lon is None:
        return None
    return lat, lon


def _has_internet_access(categories: object) -> bool | None:
    if not isinstance(categories, list):
        return None
    normalized = {
        item.strip().casefold()
        for item in categories
        if isinstance(item, str) and item.strip()
    }
    if any(item == "internet_access" or item.startswith("internet_access.") for item in normalized):
        return True
    return None


class GeoapifyProvider:
    capabilities = GEOAPIFY_CAPABILITIES

    def __init__(
        self,
        *,
        api_key: str,
        endpoint: str = "https://api.geoapify.com/v2/places",
        timeout_seconds: float = 10.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        if not api_key.strip():
            raise ValueError("Geoapify API key must not be empty")

        self._api_key = api_key.strip()
        self._endpoint = endpoint
        self._endpoint_label = endpoint_label(endpoint)
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(
            timeout=httpx.Timeout(timeout_seconds),
            headers={
                "User-Agent": "PermPlaces/0.37 (+https://github.com/KornutaKM/permplaces)"
            },
        )

    async def close(self) -> None:
        if self._owns_client:
            await self._client.aclose()

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
        categories = _CATEGORY_QUERIES.get(category)
        if categories is None or not _supports_filters(filters):
            return []

        radius = min(max(radius_m, 1), 100_000)
        result_limit = min(max(limit, 1), _MAX_RESULTS_PER_REQUEST)
        params: dict[str, str | int] = {
            "apiKey": self._api_key,
            "categories": categories,
            "filter": f"circle:{longitude:.6f},{latitude:.6f},{radius}",
            "bias": f"proximity:{longitude:.6f},{latitude:.6f}",
            "limit": result_limit,
            "lang": "ru",
        }
        wifi_required = bool(filters and filters.wifi)
        if wifi_required:
            params["conditions"] = "internet_access"

        started_at = monotonic()
        try:
            response = await self._client.get(self._endpoint, params=params)
            response.raise_for_status()
            payload = response.json()
            venues = self._parse_payload(
                payload,
                category=category,
                wifi_required=wifi_required,
            )
        except ProviderError:
            raise
        except (httpx.HTTPError, ValueError) as exc:
            elapsed_ms = round((monotonic() - started_at) * 1000)
            logger.warning(
                "geoapify_request status=failed endpoint=%s elapsed_ms=%d",
                self._endpoint_label,
                elapsed_ms,
            )
            raise ProviderError("Geoapify search is temporarily unavailable") from exc

        elapsed_ms = round((monotonic() - started_at) * 1000)
        logger.info(
            "geoapify_request status=success endpoint=%s elapsed_ms=%d venues=%d",
            self._endpoint_label,
            elapsed_ms,
            len(venues),
        )
        return venues[:result_limit]

    async def search_in_area(
        self,
        *,
        category: str,
        relation_id: int,
        limit: int,
        filters: PlaceFilters | None = None,
    ) -> list[Venue]:
        # District search is governed by exact OSM relation polygons. Geoapify
        # uses its own place identifiers, so we do not approximate a district
        # from names or bounding boxes.
        del category, relation_id, limit, filters
        return []

    @staticmethod
    def _parse_payload(
        payload: Any,
        *,
        category: str,
        wifi_required: bool,
    ) -> list[Venue]:
        if not isinstance(payload, Mapping) or payload.get("type") != "FeatureCollection":
            raise ProviderError("Geoapify returned an unexpected response")

        features = payload.get("features")
        if not isinstance(features, list):
            raise ProviderError("Geoapify returned an unexpected response")

        venues: list[Venue] = []
        seen: set[str] = set()
        for feature in features:
            if not isinstance(feature, Mapping):
                continue
            properties = feature.get("properties")
            if not isinstance(properties, Mapping):
                continue

            source_id = _clean_text(properties.get("place_id"))
            name = _clean_text(properties.get("name"))
            coords = _coordinates(feature, properties)
            if source_id is None or name is None or coords is None or source_id in seen:
                continue

            address = _clean_text(properties.get("address_line2"))
            if address is None:
                address = _clean_text(properties.get("formatted"))
            district = _clean_text(properties.get("district"))
            wifi = True if wifi_required else _has_internet_access(properties.get("categories"))
            latitude, longitude = coords

            venues.append(
                Venue(
                    id=f"geoapify:{source_id}",
                    name=name,
                    category=category,
                    category_label=_CATEGORY_NAMES.get(category, "Заведение"),
                    latitude=latitude,
                    longitude=longitude,
                    source="geoapify",
                    source_id=source_id,
                    address=address,
                    district=district,
                    wifi=wifi,
                )
            )
            seen.add(source_id)

        return venues
