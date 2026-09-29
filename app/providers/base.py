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

    async def search_in_area(
        self,
        *,
        category: str,
        relation_id: int,
        limit: int,
    ) -> list[Venue]: ...
