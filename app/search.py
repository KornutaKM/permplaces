from dataclasses import replace
from math import asin, cos, radians, sin, sqrt

from app.data import Venue
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
    ) -> list[Venue]:
        candidates = await self._provider.search_nearby(
            category=category,
            latitude=latitude,
            longitude=longitude,
            radius_m=radius_m,
            limit=max(25, limit * 4),
        )

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
