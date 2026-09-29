from __future__ import annotations

import asyncio
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass
from time import monotonic
from typing import TypeAlias

from app.data import Venue
from app.filters import PlaceFilters
from app.providers.base import PlacesProvider


CacheKey: TypeAlias = tuple[object, ...]


@dataclass(frozen=True, slots=True)
class _CacheEntry:
    expires_at: float
    venues: tuple[Venue, ...]


class CachedPlacesProvider:
    """Bounded in-memory TTL cache for read-only provider searches.

    The cache is process-local and intentionally disposable. It coalesces identical
    concurrent misses so a burst of Telegram callbacks results in one upstream request.
    """

    def __init__(
        self,
        provider: PlacesProvider,
        *,
        ttl_seconds: float = 120.0,
        max_entries: int = 256,
        clock: Callable[[], float] = monotonic,
    ) -> None:
        if ttl_seconds < 0:
            raise ValueError("ttl_seconds must be non-negative")
        if max_entries < 1:
            raise ValueError("max_entries must be positive")

        self._provider = provider
        self._ttl_seconds = ttl_seconds
        self._max_entries = max_entries
        self._clock = clock
        self._entries: OrderedDict[CacheKey, _CacheEntry] = OrderedDict()
        self._inflight: dict[CacheKey, asyncio.Task[list[Venue]]] = {}
        self._lock = asyncio.Lock()

    @staticmethod
    def _filters_key(filters: PlaceFilters | None) -> PlaceFilters:
        return filters or PlaceFilters()

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
        normalized_filters = self._filters_key(filters)
        key: CacheKey = (
            "nearby",
            category,
            latitude,
            longitude,
            radius_m,
            limit,
            normalized_filters,
        )

        async def fetch() -> list[Venue]:
            return await self._provider.search_nearby(
                category=category,
                latitude=latitude,
                longitude=longitude,
                radius_m=radius_m,
                limit=limit,
                filters=normalized_filters,
            )

        return await self._get_or_fetch(key, fetch)

    async def search_in_area(
        self,
        *,
        category: str,
        relation_id: int,
        limit: int,
        filters: PlaceFilters | None = None,
    ) -> list[Venue]:
        normalized_filters = self._filters_key(filters)
        key: CacheKey = (
            "area",
            category,
            relation_id,
            limit,
            normalized_filters,
        )

        async def fetch() -> list[Venue]:
            return await self._provider.search_in_area(
                category=category,
                relation_id=relation_id,
                limit=limit,
                filters=normalized_filters,
            )

        return await self._get_or_fetch(key, fetch)

    async def _get_or_fetch(
        self,
        key: CacheKey,
        fetch: Callable[[], object],
    ) -> list[Venue]:
        now = self._clock()

        async with self._lock:
            cached = self._entries.get(key)
            if cached is not None and cached.expires_at > now:
                self._entries.move_to_end(key)
                return list(cached.venues)

            if cached is not None:
                self._entries.pop(key, None)

            task = self._inflight.get(key)
            if task is None:
                async def run_fetch() -> list[Venue]:
                    result = fetch()
                    if not hasattr(result, "__await__"):
                        raise TypeError("fetch must return an awaitable")
                    return await result  # type: ignore[misc]

                task = asyncio.create_task(run_fetch())
                self._inflight[key] = task

        try:
            venues = await asyncio.shield(task)
        except BaseException:
            async with self._lock:
                if self._inflight.get(key) is task:
                    self._inflight.pop(key, None)
            raise

        async with self._lock:
            if self._inflight.get(key) is task:
                self._inflight.pop(key, None)
                self._entries[key] = _CacheEntry(
                    expires_at=self._clock() + self._ttl_seconds,
                    venues=tuple(venues),
                )
                self._entries.move_to_end(key)
                while len(self._entries) > self._max_entries:
                    self._entries.popitem(last=False)

        return list(venues)
