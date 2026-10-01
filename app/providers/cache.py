from __future__ import annotations

import asyncio
import logging
from collections import OrderedDict
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from time import monotonic

from app.data import Venue
from app.filters import PlaceFilters
from app.providers.base import PlacesProvider
from app.providers.capabilities import ProviderCapabilities, provider_capabilities

type CacheKey = tuple[object, ...]

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class _CacheEntry:
    expires_at: float
    venues: tuple[Venue, ...]


@dataclass(frozen=True, slots=True)
class CacheStats:
    hits: int
    misses: int
    coalesced: int
    evictions: int
    entries: int
    inflight: int


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
        self._hits = 0
        self._misses = 0
        self._coalesced = 0
        self._evictions = 0

    @property
    def capabilities(self) -> ProviderCapabilities:
        return provider_capabilities(self._provider)

    def stats(self) -> CacheStats:
        return CacheStats(
            hits=self._hits,
            misses=self._misses,
            coalesced=self._coalesced,
            evictions=self._evictions,
            entries=len(self._entries),
            inflight=len(self._inflight),
        )

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
        fetch: Callable[[], Awaitable[list[Venue]]],
    ) -> list[Venue]:
        now = self._clock()

        async with self._lock:
            cached = self._entries.get(key)
            if cached is not None and cached.expires_at > now:
                self._entries.move_to_end(key)
                self._hits += 1
                logger.info(
                    "provider_cache event=hit entries=%d inflight=%d",
                    len(self._entries),
                    len(self._inflight),
                )
                return list(cached.venues)

            if cached is not None:
                self._entries.pop(key, None)

            task = self._inflight.get(key)
            if task is None:
                self._misses += 1
                task = asyncio.create_task(fetch())
                self._inflight[key] = task
                logger.info(
                    "provider_cache event=miss entries=%d inflight=%d",
                    len(self._entries),
                    len(self._inflight),
                )
            else:
                self._coalesced += 1
                logger.info(
                    "provider_cache event=coalesced entries=%d inflight=%d",
                    len(self._entries),
                    len(self._inflight),
                )

        try:
            venues = await asyncio.shield(task)
        except asyncio.CancelledError:
            # Cancelling one Telegram handler must not cancel or invalidate the
            # shared upstream request awaited by other handlers.
            raise
        except Exception:
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
                    self._evictions += 1
                    logger.info(
                        "provider_cache event=eviction entries=%d max_entries=%d",
                        len(self._entries),
                        self._max_entries,
                    )

        return list(venues)
