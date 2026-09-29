from typing import Protocol

from app.data import Venue


class PlacesProvider(Protocol):
    async def search_nearby(
        self,
        *,
        category: str,
        latitude: float,
        longitude: float,
        radius_m: int,
        limit: int,
    ) -> list[Venue]: ...
