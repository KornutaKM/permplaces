from typing import Protocol

from app.data import Venue
from app.filters import PlaceFilters


class ProviderError(RuntimeError):
    """Raised when an external places provider cannot return a usable response."""


class PlacesProvider(Protocol):
    async def search_nearby(
        self,
        *,
        category: str,
        latitude: float,
        longitude: float,
        radius_m: int,
        limit: int,
        filters: PlaceFilters | None = None,
    ) -> list[Venue]: ...

    async def search_in_area(
        self,
        *,
        category: str,
        relation_id: int,
        limit: int,
        filters: PlaceFilters | None = None,
    ) -> list[Venue]: ...
