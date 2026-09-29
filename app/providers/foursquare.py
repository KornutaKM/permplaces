from __future__ import annotations

import logging
from collections.abc import Mapping
from datetime import datetime
from time import monotonic
from typing import Any
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

import httpx

from app.data import Venue
from app.filters import PlaceFilters
from app.observability import endpoint_label
from app.providers.base import ProviderError

logger = logging.getLogger(__name__)

_API_VERSION = "2025-06-17"
_PERM_TIMEZONE = ZoneInfo("Asia/Yekaterinburg")
_FIELDS = (
    "fsq_place_id,name,latitude,longitude,location,tel,website,menu,"
    "rating,price,stats,attributes,hours"
)

_CATEGORY_QUERIES = {
    "restaurant": "restaurant",
    "cafe": "coffee",
    "bar": "bar",
    "fastfood": "fast food",
    "pizza": "pizza",
    "sushi": "sushi",
    "breakfast": "breakfast",
    "dessert": "dessert",
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

_POSITIVE_WIFI = {"available", "free", "paid", "true", "yes"}


def late_open_at(now: datetime | None = None) -> str:
    if now is None:
        local = datetime.now(_PERM_TIMEZONE)
    elif now.tzinfo is None:
        local = now.replace(tzinfo=_PERM_TIMEZONE)
    else:
        local = now.astimezone(_PERM_TIMEZONE)
    return f"{local.isoweekday()}T2300"


def _supports_filters(filters: PlaceFilters | None) -> bool:
    if filters is None:
        return True
    if filters.family_friendly:
        return False
    return not (filters.open_now and filters.open_late)


def _clean_text(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = value.strip()
    return cleaned or None


def _http_url(value: object) -> str | None:
    cleaned = _clean_text(value)
    if cleaned is None:
        return None
    parsed = urlsplit(cleaned)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None
    return cleaned


def _wifi_state(value: object) -> bool | None:
    if isinstance(value, bool):
        return value
    if not isinstance(value, str):
        return None
    normalized = value.strip().casefold()
    if normalized in _POSITIVE_WIFI:
        return True
    if normalized in {"false", "no", "none", "unavailable"}:
        return False
    return None


def _rating(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    rating = float(value)
    return rating if 0.0 <= rating <= 10.0 else None


def _review_count(stats: object) -> int | None:
    if not isinstance(stats, Mapping):
        return None
    value = stats.get("total_ratings")
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value


def _price_label(value: object) -> str | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    if not 1 <= value <= 4:
        return None
    return "₽" * value


class FoursquareProvider:
    def __init__(
        self,
        *,
        api_key: str,
        endpoint: str = "https://places-api.foursquare.com/places/search",
        timeout_seconds: float = 10.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        if not api_key.strip():
            raise ValueError("Foursquare API key must not be empty")

        self._endpoint = endpoint
        self._endpoint_label = endpoint_label(endpoint)
        self._headers = {
            "Accept": "application/json",
            "Authorization": f"Bearer {api_key.strip()}",
            "User-Agent": "PermPlaces/0.21 (+https://github.com/KornutaKM/permplaces)",
            "X-Places-Api-Version": _API_VERSION,
        }
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(
            timeout=httpx.Timeout(timeout_seconds),
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
            "query": query,
            "ll": f"{latitude:.6f},{longitude:.6f}",
            "radius": min(max(radius_m, 1), 100_000),
            "limit": min(max(limit, 1), 50),
            "sort": "DISTANCE",
            "fields": _FIELDS,
        }
        if filters and filters.open_now:
            params["open_now"] = "true"
        elif filters and filters.open_late:
            params["open_at"] = late_open_at()

        started_at = monotonic()
        try:
            response = await self._client.get(
                self._endpoint,
                params=params,
                headers=self._headers,
            )
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            elapsed_ms = round((monotonic() - started_at) * 1000)
            logger.warning(
                "foursquare_request status=failed endpoint=%s elapsed_ms=%d",
                self._endpoint_label,
                elapsed_ms,
            )
            raise ProviderError("Foursquare search is temporarily unavailable") from exc

        venues = self._parse_payload(payload, category=category, filters=filters)
        elapsed_ms = round((monotonic() - started_at) * 1000)
        logger.info(
            "foursquare_request status=success endpoint=%s elapsed_ms=%d venues=%d",
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
        # District search is bound to exact OSM relation polygons. Foursquare
        # cannot consume that relation identity, so it deliberately stays out.
        del category, relation_id, limit, filters
        return []

    @staticmethod
    def _parse_payload(
        payload: Any,
        *,
        category: str,
        filters: PlaceFilters | None,
    ) -> list[Venue]:
        if not isinstance(payload, Mapping):
            raise ProviderError("Foursquare returned an unexpected response")

        results = payload.get("results")
        if not isinstance(results, list):
            raise ProviderError("Foursquare returned an unexpected response")

        venues: list[Venue] = []
        for item in results:
            if not isinstance(item, Mapping):
                continue

            source_id = item.get("fsq_place_id")
            name = _clean_text(item.get("name"))
            lat = item.get("latitude")
            lon = item.get("longitude")
            if (
                not isinstance(source_id, str)
                or not source_id.strip()
                or name is None
                or isinstance(lat, bool)
                or isinstance(lon, bool)
                or not isinstance(lat, (int, float))
                or not isinstance(lon, (int, float))
            ):
                continue

            attributes = item.get("attributes")
            if not isinstance(attributes, Mapping):
                attributes = {}
            outdoor = attributes.get("outdoor_seating")
            outdoor_state = outdoor if isinstance(outdoor, bool) else None
            wifi_state = _wifi_state(attributes.get("wifi"))

            if filters and filters.outdoor_seating and outdoor_state is not True:
                continue
            if filters and filters.wifi and wifi_state is not True:
                continue

            hours = item.get("hours")
            if not isinstance(hours, Mapping):
                hours = {}
            provider_open_now = hours.get("open_now")
            if not isinstance(provider_open_now, bool):
                provider_open_now = None

            location = item.get("location")
            if not isinstance(location, Mapping):
                location = {}
            address = _clean_text(location.get("formatted_address"))
            if address is None:
                address = _clean_text(location.get("address"))

            rating = _rating(item.get("rating"))
            reviews = _review_count(item.get("stats"))

            venues.append(
                Venue(
                    id=f"foursquare:{source_id}",
                    name=name,
                    category=category,
                    category_label=_CATEGORY_NAMES.get(category, "Заведение"),
                    latitude=float(lat),
                    longitude=float(lon),
                    source="foursquare",
                    source_id=source_id.strip(),
                    address=address,
                    opening_hours=_clean_text(hours.get("display")),
                    is_open_now=True
                    if filters and filters.open_now
                    else provider_open_now,
                    is_open_late=True if filters and filters.open_late else None,
                    phone=_clean_text(item.get("tel")),
                    website=_clean_text(item.get("website")),
                    menu_url=_http_url(item.get("menu")),
                    outdoor_seating=outdoor_state,
                    wifi=wifi_state,
                    price_label=_price_label(item.get("price")),
                    rating=rating,
                    rating_scale=10.0 if rating is not None else None,
                    review_count=reviews if rating is not None else None,
                )
            )

        return venues
