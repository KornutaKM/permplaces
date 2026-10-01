from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

import aiosqlite

from app.data import Venue
from app.database import initialize_database
from app.filters import PlaceFilters
from app.providers.base import PlacesProvider, ProviderError
from app.providers.capabilities import ProviderCapabilities, provider_capabilities


@dataclass(frozen=True, slots=True)
class DailyBudgetStatus:
    provider: str
    day: str
    used: int
    limit: int

    @property
    def remaining(self) -> int:
        return max(0, self.limit - self.used)


def render_daily_budget_status(status: DailyBudgetStatus) -> str:
    return (
        "локальный лимит: "
        f"{status.used}/{status.limit}; "
        f"осталось {status.remaining}; UTC-день {status.day}"
    )


class SQLiteDailyRequestBudget:
    """Persistent application-side request guard keyed by UTC calendar day."""

    def __init__(
        self,
        database_path: str,
        *,
        provider: str,
        daily_limit: int,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        if daily_limit < 1:
            raise ValueError("daily_limit must be positive")
        if not provider.strip():
            raise ValueError("provider must not be empty")

        self._database_path = database_path
        self._provider = provider.strip()
        self._daily_limit = daily_limit
        self._clock = clock or (lambda: datetime.now(UTC))

    def _day(self) -> str:
        current = self._clock()
        if current.tzinfo is None:
            current = current.replace(tzinfo=UTC)
        return current.astimezone(UTC).date().isoformat()

    async def initialize(self) -> None:
        await initialize_database(self._database_path)

    async def reserve(self) -> DailyBudgetStatus:
        day = self._day()

        async with aiosqlite.connect(self._database_path) as database:
            await database.execute("PRAGMA busy_timeout=5000")
            await database.execute("BEGIN IMMEDIATE")

            cursor = await database.execute(
                """
                SELECT used
                FROM provider_daily_request_budget
                WHERE provider = ? AND day = ?
                """,
                (self._provider, day),
            )
            row = await cursor.fetchone()
            await cursor.close()

            used = int(row[0]) if row is not None else 0
            if used >= self._daily_limit:
                await database.rollback()
                raise ProviderError(
                    f"{self._provider} local daily request budget exhausted"
                )

            new_used = used + 1
            await database.execute(
                """
                INSERT INTO provider_daily_request_budget (provider, day, used)
                VALUES (?, ?, ?)
                ON CONFLICT(provider, day) DO UPDATE SET
                    used = excluded.used
                """,
                (self._provider, day, new_used),
            )
            await database.commit()

        return DailyBudgetStatus(
            provider=self._provider,
            day=day,
            used=new_used,
            limit=self._daily_limit,
        )

    async def status(self) -> DailyBudgetStatus:
        day = self._day()
        async with aiosqlite.connect(self._database_path) as database:
            cursor = await database.execute(
                """
                SELECT used
                FROM provider_daily_request_budget
                WHERE provider = ? AND day = ?
                """,
                (self._provider, day),
            )
            row = await cursor.fetchone()
            await cursor.close()

        return DailyBudgetStatus(
            provider=self._provider,
            day=day,
            used=int(row[0]) if row is not None else 0,
            limit=self._daily_limit,
        )


class DailyBudgetPlacesProvider:
    """Reserve one local request unit immediately before an upstream provider call."""

    def __init__(
        self,
        provider: PlacesProvider,
        *,
        budget: SQLiteDailyRequestBudget,
    ) -> None:
        self._provider = provider
        self._budget = budget

    @property
    def capabilities(self) -> ProviderCapabilities:
        return provider_capabilities(self._provider)

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
        await self._budget.reserve()
        return await self._provider.search_nearby(
            category=category,
            latitude=latitude,
            longitude=longitude,
            radius_m=radius_m,
            limit=limit,
            filters=filters,
        )

    async def search_in_area(
        self,
        *,
        category: str,
        relation_id: int,
        limit: int,
        filters: PlaceFilters | None = None,
    ) -> list[Venue]:
        await self._budget.reserve()
        return await self._provider.search_in_area(
            category=category,
            relation_id=relation_id,
            limit=limit,
            filters=filters,
        )
