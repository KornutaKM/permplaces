from dataclasses import replace
from datetime import UTC, datetime
from math import asin, cos, radians, sin, sqrt

from app.data import Venue
from app.filters import PlaceFilters
from app.opening import OpeningState, opening_state
from app.providers.base import PlacesProvider


def distance_m(
    latitude_a: float,
    longitude_a: float,
    latitude_b: float,
    longitude_b: float,
) -> int:
    earth_radius_m = 6_371_000
    lat1 = radians(latitude_a)
    lat2 = radians(latitude_b)
    dlat = radians(latitude_b - latitude_a)
    dlon = radians(longitude_b - longitude_a)

    haversine = (
        sin(dlat / 2) ** 2
        + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
    )
    return round(2 * earth_radius_m * asin(sqrt(haversine)))


def _filter_open_now(
    venues: list[Venue],
    *,
    filters: PlaceFilters | None,
) -> list[Venue]:
    if filters is None or not filters.open_now:
        return venues

    at = datetime.now(UTC)
    opened: list[Venue] = []
    for venue in venues:
        state = opening_state(
            venue.opening_hours,
            latitude=venue.latitude,
            longitude=venue.longitude,
            at=at,
        )
        if state is OpeningState.OPEN:
            opened.append(replace(venue, is_open_now=True))
    return opened


class SearchService:
    def __init__(self, provider: PlacesProvider) -> None:
        self._provider = provider

    async def nearby(
        self,
        *,
        category: str,
        latitude: float,
        longitude: float,
        radius_m: int = 3000,
        limit: int = 5,
        filters: PlaceFilters | None = None,
    ) -> list[Venue]:
        provider_limit = (
            max(80, limit * 16)
            if filters is not None and filters.open_now
            else max(25, limit * 4)
        )
        candidates = await self._provider.search_nearby(
            category=category,
            latitude=latitude,
            longitude=longitude,
            radius_m=radius_m,
            limit=provider_limit,
            filters=filters,
        )
        candidates = _filter_open_now(candidates, filters=filters)

        with_distance = [
            replace(
                venue,
                distance_m=distance_m(
                    latitude,
                    longitude,
                    venue.latitude,
                    venue.longitude,
                ),
            )
            for venue in candidates
        ]
        in_radius = [
            venue
            for venue in with_distance
            if venue.distance_m is not None and venue.distance_m <= radius_m
        ]
        return sorted(
            in_radius,
            key=lambda venue: (venue.distance_m or 0, venue.name.casefold()),
        )[:limit]

    async def in_district(
        self,
        *,
        category: str,
        relation_id: int,
        district_name: str,
        limit: int = 5,
        filters: PlaceFilters | None = None,
    ) -> list[Venue]:
        provider_limit = (
            max(150, limit * 30)
            if filters is not None and filters.open_now
            else max(50, limit * 10)
        )
        candidates = await self._provider.search_in_area(
            category=category,
            relation_id=relation_id,
            limit=provider_limit,
            filters=filters,
        )
        candidates = _filter_open_now(candidates, filters=filters)
        normalized = [
            replace(venue, district=district_name, distance_m=None)
            for venue in candidates
        ]
        return sorted(
            normalized,
            key=lambda venue: (venue.name.casefold(), venue.source_id),
        )[:limit]
