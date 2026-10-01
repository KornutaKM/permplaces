from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable, Sequence

from app.data import Venue
from app.dedup import merge_provider_results
from app.filters import PlaceFilters
from app.providers.base import PlacesProvider, ProviderError
from app.providers.capabilities import provider_capabilities

logger = logging.getLogger(__name__)


class CompositePlacesProvider:
    """Aggregate independent providers in deterministic priority order."""

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
        selected = tuple(
            provider
            for provider in self._providers
            if provider_capabilities(provider).supports_nearby(
                category=category,
                filters=filters,
            )
        )
        if not selected:
            return []

        async def call(provider: PlacesProvider) -> list[Venue]:
            return await provider.search_nearby(
                category=category,
                latitude=latitude,
                longitude=longitude,
                radius_m=radius_m,
                limit=limit,
                filters=filters,
            )

        return await self._collect(selected, call, limit=limit)

    async def search_in_area(
        self,
        *,
        category: str,
        relation_id: int,
        limit: int,
        filters: PlaceFilters | None = None,
    ) -> list[Venue]:
        selected = tuple(
            provider
            for provider in self._providers
            if provider_capabilities(provider).supports_area(
                category=category,
                filters=filters,
            )
        )
        if not selected:
            return []

        async def call(provider: PlacesProvider) -> list[Venue]:
            return await provider.search_in_area(
                category=category,
                relation_id=relation_id,
                limit=limit,
                filters=filters,
            )

        return await self._collect(selected, call, limit=limit)

    async def _collect(
        self,
        providers: Sequence[PlacesProvider],
        call: Callable[[PlacesProvider], Awaitable[list[Venue]]],
        *,
        limit: int,
    ) -> list[Venue]:
        results = await asyncio.gather(
            *(call(provider) for provider in providers),
            return_exceptions=True,
        )

        successful: list[list[Venue]] = []
        failures = 0
        for index, result in enumerate(results):
            if isinstance(result, ProviderError):
                failures += 1
                logger.warning(
                    "places_composite event=provider_failed provider_index=%d providers_total=%d",
                    index,
                    len(providers),
                )
                continue
            if isinstance(result, BaseException):
                raise result
            successful.append(result)

        if not successful:
            raise ProviderError(
                f"all configured aggregate providers failed ({failures})"
            )

        if failures:
            logger.info(
                "places_composite event=partial_success successful=%d failed=%d",
                len(successful),
                failures,
            )

        return merge_provider_results(successful, limit=limit)
