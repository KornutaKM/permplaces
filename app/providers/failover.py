from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable, Sequence

from app.data import Venue
from app.filters import PlaceFilters
from app.providers.base import PlacesProvider, ProviderError

logger = logging.getLogger(__name__)


class FailoverPlacesProvider:
    """Try configured providers in order and fail closed when all are unavailable."""

    def __init__(self, providers: Sequence[PlacesProvider]) -> None:
        if not providers:
            raise ValueError("at least one provider is required")
        self._providers = tuple(providers)

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
        async def search(provider: PlacesProvider) -> list[Venue]:
            return await provider.search_nearby(
                category=category,
                latitude=latitude,
                longitude=longitude,
                radius_m=radius_m,
                limit=limit,
                filters=filters,
            )

        return await self._try_providers(search)

    async def search_in_area(
        self,
        *,
        category: str,
        relation_id: int,
        limit: int,
        filters: PlaceFilters | None = None,
    ) -> list[Venue]:
        async def search(provider: PlacesProvider) -> list[Venue]:
            return await provider.search_in_area(
                category=category,
                relation_id=relation_id,
                limit=limit,
                filters=filters,
            )

        return await self._try_providers(search)

    async def _try_providers(
        self,
        search: Callable[[PlacesProvider], Awaitable[list[Venue]]],
    ) -> list[Venue]:
        errors: list[ProviderError] = []

        for index, provider in enumerate(self._providers):
            try:
                return await search(provider)
            except ProviderError as exc:
                errors.append(exc)
                logger.warning(
                    "places provider failed; trying next configured provider",
                    extra={
                        "provider_index": index,
                        "providers_total": len(self._providers),
                    },
                )

        raise ProviderError(
            f"all configured places providers failed ({len(errors)})"
        ) from errors[-1]
