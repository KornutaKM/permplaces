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
from app.providers.capabilities import OVERPASS_CAPABILITIES

logger = logging.getLogger(__name__)

_CATEGORY_FILTERS = {
    "restaurant": '["amenity"="restaurant"]',
    "cafe": '["amenity"="cafe"]',
    "bar": '["amenity"~"^(bar|pub)$"]',
    "fastfood": '["amenity"="fast_food"]',
    "pizza": '["amenity"~"^(restaurant|fast_food)$"]["cuisine"~"pizza",i]',
    "sushi": '["amenity"~"^(restaurant|fast_food)$"]["cuisine"~"(sushi|japanese)",i]',
    "breakfast": '["amenity"~"^(cafe|restaurant)$"]["breakfast"="yes"]',
    "dessert": '["amenity"~"^(cafe|ice_cream)$"]',
    "food_drink": '["amenity"~"^(restaurant|cafe|bar|pub|fast_food|ice_cream)$"]',
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
    "food_drink": "Заведение",
}


def _category_filter(category: str) -> str:
    tag_filter = _CATEGORY_FILTERS.get(category)
    if tag_filter is None:
        raise ValueError(f"Unsupported category: {category}")
    return tag_filter


def _filter_suffixes(filters: PlaceFilters | None) -> tuple[str, ...]:
    active = filters or PlaceFilters()
    common = ""
    if active.outdoor_seating:
        common += '["outdoor_seating"]["outdoor_seating"!="no"]'
    if active.open_now or active.open_late:
        common += '["opening_hours"]'

    suffixes = [common]

    if active.wifi:
        suffixes = [
            prefix + wifi_filter
            for prefix in suffixes
            for wifi_filter in (
                '["internet_access"~"(^|;)wlan(;|$)",i]',
                '["wifi"~"^(yes|free)$",i]',
            )
        ]

    if active.family_friendly:
        suffixes = [
            prefix + family_filter
            for prefix in suffixes
            for family_filter in (
                '["kids_area"~"^(yes|designated|limited)$",i]',
                '["highchair"~"^(yes|[1-9][0-9]*)$",i]',
                '["changing_table"~"^(yes|limited)$",i]',
            )
        ]

    return tuple(suffixes)


def build_overpass_query(
    *,
    category: str,
    latitude: float,
    longitude: float,
    radius_m: int,
    filters: PlaceFilters | None = None,
) -> str:
    tag_filter = _category_filter(category)
    selectors = "\n".join(
        (
            f'  nwr(around:{radius_m},{latitude:.6f},{longitude:.6f})'
            f"{tag_filter}{suffix};"
        )
        for suffix in _filter_suffixes(filters)
    )
    return (
        "[out:json][timeout:20];\n"
        "(\n"
        f"{selectors}\n"
        ");\n"
        "out center tags;"
    )


def build_area_query(
    *,
    category: str,
    relation_id: int,
    filters: PlaceFilters | None = None,
) -> str:
    if relation_id <= 0:
        raise ValueError("relation_id must be positive")

    tag_filter = _category_filter(category)
    selectors = "\n".join(
        f"  nwr(area.searchArea){tag_filter}{suffix};"
        for suffix in _filter_suffixes(filters)
    )
    return (
        "[out:json][timeout:25];\n"
        f"rel({relation_id});\n"
        "map_to_area -> .searchArea;\n"
        "(\n"
        f"{selectors}\n"
        ");\n"
        "out center tags;"
    )


def _coordinates(element: Mapping[str, Any]) -> tuple[float, float] | None:
    if "lat" in element and "lon" in element:
        return float(element["lat"]), float(element["lon"])

    center = element.get("center")
    if isinstance(center, Mapping) and "lat" in center and "lon" in center:
        return float(center["lat"]), float(center["lon"])

    return None


def _address(tags: Mapping[str, Any]) -> str | None:
    full = tags.get("addr:full")
    if isinstance(full, str) and full.strip():
        return full.strip()

    street = tags.get("addr:street")
    house = tags.get("addr:housenumber")
    parts = [
        value.strip()
        for value in (street, house)
        if isinstance(value, str) and value.strip()
    ]
    return ", ".join(parts) or None


def _split_tag(value: Any) -> tuple[str, ...]:
    if not isinstance(value, str):
        return ()
    return tuple(part.strip() for part in value.split(";") if part.strip())


def _outdoor_seating(tags: Mapping[str, Any]) -> bool | None:
    value = tags.get("outdoor_seating")
    if not isinstance(value, str) or not value.strip():
        return None
    return value.strip().casefold() != "no"


def _positive_enum_tag(
    tags: Mapping[str, Any],
    key: str,
    *,
    positive: set[str],
) -> bool | None:
    value = tags.get(key)
    if not isinstance(value, str) or not value.strip():
        return None

    normalized = value.strip().casefold()
    if normalized in positive:
        return True
    if normalized == "no":
        return False
    return None


def _highchair(tags: Mapping[str, Any]) -> bool | None:
    value = tags.get("highchair")
    if not isinstance(value, str) or not value.strip():
        return None

    normalized = value.strip().casefold()
    if normalized == "yes":
        return True
    if normalized == "no":
        return False
    try:
        return int(normalized) > 0
    except ValueError:
        return None


def _wifi(tags: Mapping[str, Any]) -> bool | None:
    internet_access = tags.get("internet_access")
    legacy_wifi = tags.get("wifi")

    internet_value = (
        internet_access.strip().casefold()
        if isinstance(internet_access, str)
        else None
    )
    wifi_value = legacy_wifi.strip().casefold() if isinstance(legacy_wifi, str) else None

    internet_tokens = {
        token.strip()
        for token in (internet_value or "").split(";")
        if token.strip()
    }
    if "wlan" in internet_tokens or wifi_value in {"yes", "free"}:
        return True

    if internet_value == "no" or wifi_value == "no":
        return False

    return None


class OverpassProvider:
    capabilities = OVERPASS_CAPABILITIES

    def __init__(
        self,
        *,
        endpoint: str,
        timeout_seconds: float = 20.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._endpoint = endpoint
        self._endpoint_label = endpoint_label(endpoint)
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(
            timeout=httpx.Timeout(timeout_seconds),
            headers={"User-Agent": "PermPlaces/0.14 (+https://github.com/KornutaKM/permplaces)"},
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
        query = build_overpass_query(
            category=category,
            latitude=latitude,
            longitude=longitude,
            radius_m=radius_m,
            filters=filters,
        )
        return await self._execute(query=query, category=category, limit=limit)

    async def search_in_area(
        self,
        *,
        category: str,
        relation_id: int,
        limit: int,
        filters: PlaceFilters | None = None,
    ) -> list[Venue]:
        query = build_area_query(
            category=category,
            relation_id=relation_id,
            filters=filters,
        )
        return await self._execute(query=query, category=category, limit=limit)

    async def _execute(
        self,
        *,
        query: str,
        category: str,
        limit: int,
    ) -> list[Venue]:
        started_at = monotonic()
        try:
            response = await self._client.post(self._endpoint, data={"data": query})
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            elapsed_ms = round((monotonic() - started_at) * 1000)
            logger.warning(
                "overpass_request status=failed endpoint=%s elapsed_ms=%d",
                self._endpoint_label,
                elapsed_ms,
            )
            raise ProviderError("OpenStreetMap search is temporarily unavailable") from exc

        if not isinstance(payload, Mapping):
            elapsed_ms = round((monotonic() - started_at) * 1000)
            logger.warning(
                "overpass_request status=invalid_payload endpoint=%s elapsed_ms=%d",
                self._endpoint_label,
                elapsed_ms,
            )
            raise ProviderError("OpenStreetMap returned an unexpected response")

        elements = payload.get("elements")
        if not isinstance(elements, list):
            elapsed_ms = round((monotonic() - started_at) * 1000)
            logger.warning(
                "overpass_request status=invalid_elements endpoint=%s elapsed_ms=%d",
                self._endpoint_label,
                elapsed_ms,
            )
            raise ProviderError("OpenStreetMap returned an unexpected response")

        venues: list[Venue] = []
        seen: set[str] = set()
        for element in elements:
            if not isinstance(element, Mapping):
                continue
            venue = self._parse_element(element, category)
            if venue is None or venue.id in seen:
                continue
            seen.add(venue.id)
            venues.append(venue)
            if len(venues) >= limit:
                break

        elapsed_ms = round((monotonic() - started_at) * 1000)
        logger.info(
            "overpass_request status=success endpoint=%s elapsed_ms=%d venues=%d",
            self._endpoint_label,
            elapsed_ms,
            len(venues),
        )
        return venues

    @staticmethod
    def _parse_element(element: Mapping[str, Any], category: str) -> Venue | None:
        coords = _coordinates(element)
        tags = element.get("tags")
        if coords is None or not isinstance(tags, Mapping):
            return None

        name = tags.get("name") or tags.get("brand")
        if not isinstance(name, str) or not name.strip():
            return None

        element_type = element.get("type")
        element_id = element.get("id")
        if element_type not in {"node", "way", "relation"} or not isinstance(element_id, int):
            return None

        latitude, longitude = coords
        source_id = f"{element_type}/{element_id}"

        return Venue(
            id=f"osm:{source_id}",
            name=name.strip(),
            category=category,
            category_label=_CATEGORY_NAMES.get(category, "Заведение"),
            latitude=latitude,
            longitude=longitude,
            source="osm",
            source_id=source_id,
            source_url=f"https://www.openstreetmap.org/{element_type}/{element_id}",
            address=_address(tags),
            district=(
                tags.get("addr:district").strip()
                if isinstance(tags.get("addr:district"), str)
                else None
            ),
            opening_hours=(
                tags.get("opening_hours").strip()
                if isinstance(tags.get("opening_hours"), str)
                else None
            ),
            phone=(
                (tags.get("contact:phone") or tags.get("phone")).strip()
                if isinstance(tags.get("contact:phone") or tags.get("phone"), str)
                else None
            ),
            website=(
                (tags.get("contact:website") or tags.get("website")).strip()
                if isinstance(tags.get("contact:website") or tags.get("website"), str)
                else None
            ),
            cuisine=_split_tag(tags.get("cuisine")),
            outdoor_seating=_outdoor_seating(tags),
            wifi=_wifi(tags),
            kids_area=_positive_enum_tag(
                tags,
                "kids_area",
                positive={"yes", "designated", "limited"},
            ),
            highchair=_highchair(tags),
            changing_table=_positive_enum_tag(
                tags,
                "changing_table",
                positive={"yes", "limited"},
            ),
        )
