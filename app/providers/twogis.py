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
from app.providers.capabilities import TWOGIS_CAPABILITIES

logger = logging.getLogger(__name__)

_CATEGORY_QUERIES = {
    "restaurant": "ресторан",
    "cafe": "кафе",
    "bar": "бар",
    "fastfood": "фастфуд",
    "pizza": "пицца",
    "sushi": "суши",
    "breakfast": "завтрак",
    "dessert": "десерты",
}

_CATEGORY_NAMES = {
    "restaurant": "Ресторан",
    "cafe": "Кофейня",
    "bar": "Бар",
    "fastfood": "Фастфуд",
    "pizza": "Пицца",
    "sushi": "Суши",
    "breakfast": "Завтраки",
    "dessert": "Десерты",
}


def _supports_filters(filters: PlaceFilters | None) -> bool:
    if filters is None:
        return True
    if filters.outdoor_seating or filters.wifi or filters.family_friendly:
        return False
    # One API request can express one work_time predicate. Combined now+23:00
    # remains OSM-only until the provider can prove both conditions.
    return not (filters.open_now and filters.open_late)


def _work_time(filters: PlaceFilters | None) -> str | None:
    if filters is None:
        return None
    if filters.open_now:
        return "now"
    if filters.open_late:
        return "today,23:00"
    return None


class TwoGISProvider:
    capabilities = TWOGIS_CAPABILITIES

    def __init__(
        self,
        *,
        api_key: str,
        endpoint: str = "https://catalog.api.2gis.com/3.0/items",
        timeout_seconds: float = 10.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        if not api_key.strip():
            raise ValueError("2GIS API key must not be empty")

        self._api_key = api_key.strip()
        self._endpoint = endpoint
        self._endpoint_label = endpoint_label(endpoint)
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(
            timeout=httpx.Timeout(timeout_seconds),
            headers={"User-Agent": "PermPlaces/0.28 (+https://github.com/KornutaKM/permplaces)"},
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
        query = _CATEGORY_QUERIES.get(category)
        if query is None or not _supports_filters(filters):
            return []

        params: dict[str, str | int] = {
            "key": self._api_key,
            "q": query,
            "type": "branch",
            "point": f"{longitude:.6f},{latitude:.6f}",
            "radius": min(max(radius_m, 0), 50_000),
            # Demo keys allow at most 10 results per page; production keys may
            # allow more. Staying at 10 keeps the adapter compatible with both.
            "page_size": min(max(limit, 1), 10),
            "locale": "ru_RU",
            "fields": "items.point",
            "search_nearby": "true",
        }
        work_time = _work_time(filters)
        if work_time:
            params["work_time"] = work_time

        started_at = monotonic()
        try:
            response = await self._client.get(self._endpoint, params=params)
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            elapsed_ms = round((monotonic() - started_at) * 1000)
            logger.warning(
                "twogis_request status=failed endpoint=%s elapsed_ms=%d",
                self._endpoint_label,
                elapsed_ms,
            )
            raise ProviderError("2GIS search is temporarily unavailable") from exc

        venues = self._parse_payload(
            payload,
            category=category,
            open_now=bool(filters and filters.open_now),
            open_late=bool(filters and filters.open_late),
        )
        elapsed_ms = round((monotonic() - started_at) * 1000)
        logger.info(
            "twogis_request status=success endpoint=%s elapsed_ms=%d venues=%d",
            self._endpoint_label,
            elapsed_ms,
            len(venues),
        )
        return venues[:limit]

    async def search_in_area(
        self,
        *,
        category: str,
        relation_id: int,
        limit: int,
        filters: PlaceFilters | None = None,
    ) -> list[Venue]:
        # The app's district authority is the exact OSM relation polygon. 2GIS
        # does not consume that relation ID directly, so v0.16 intentionally
        # stays out of district search rather than using an approximate text
        # georestriction.
        del category, relation_id, limit, filters
        return []

    @staticmethod
    def _parse_payload(
        payload: Any,
        *,
        category: str,
        open_now: bool,
        open_late: bool,
    ) -> list[Venue]:
        if not isinstance(payload, Mapping):
            raise ProviderError("2GIS returned an unexpected response")

        meta = payload.get("meta")
        if not isinstance(meta, Mapping) or meta.get("code") != 200:
            raise ProviderError("2GIS returned an unsuccessful response")

        result = payload.get("result")
        if not isinstance(result, Mapping):
            raise ProviderError("2GIS returned an unexpected response")

        items = result.get("items")
        if not isinstance(items, list):
            raise ProviderError("2GIS returned an unexpected response")

        venues: list[Venue] = []
        for item in items:
            if not isinstance(item, Mapping) or item.get("type") != "branch":
                continue

            source_id = item.get("id")
            name = item.get("name")
            point = item.get("point")
            if (
                not isinstance(source_id, str)
                or not isinstance(name, str)
                or not isinstance(point, Mapping)
            ):
                continue

            lat = point.get("lat")
            lon = point.get("lon")
            if not isinstance(lat, (int, float)) or not isinstance(lon, (int, float)):
                continue

            address = item.get("address_name")
            venues.append(
                Venue(
                    id=f"2gis:{source_id}",
                    name=name.strip(),
                    category=category,
                    category_label=_CATEGORY_NAMES.get(category, "Заведение"),
                    latitude=float(lat),
                    longitude=float(lon),
                    source="2gis",
                    source_id=source_id,
                    address=address.strip() if isinstance(address, str) and address.strip() else None,
                    is_open_now=True if open_now else None,
                    is_open_late=True if open_late else None,
                )
            )

        return venues
