from datetime import UTC, datetime

import pytest

from app.data import Venue
from app.filters import PlaceFilters
from app.providers.base import ProviderError
from app.providers.budget import DailyBudgetPlacesProvider, SQLiteDailyRequestBudget
from app.providers.capabilities import ProviderCapabilities


class FakeProvider:
    capabilities = ProviderCapabilities(
        categories=frozenset({"cafe"}),
        nearby_search=True,
    )

    def __init__(self) -> None:
        self.calls = 0

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
        del category, latitude, longitude, radius_m, limit, filters
        self.calls += 1
        return []

    async def search_in_area(
        self,
        *,
        category: str,
        relation_id: int,
        limit: int,
        filters: PlaceFilters | None = None,
    ) -> list[Venue]:
        del category, relation_id, limit, filters
        self.calls += 1
        return []


@pytest.mark.asyncio
async def test_daily_budget_persists_and_blocks_before_upstream_call(tmp_path) -> None:
    database = str(tmp_path / "permplaces.db")
    now = datetime(2026, 10, 1, 12, tzinfo=UTC)
    budget = SQLiteDailyRequestBudget(
        database,
        provider="geoapify",
        daily_limit=2,
        clock=lambda: now,
    )
    await budget.initialize()

    provider = FakeProvider()
    guarded = DailyBudgetPlacesProvider(provider, budget=budget)

    for _ in range(2):
        await guarded.search_nearby(
            category="cafe",
            latitude=58.01,
            longitude=56.25,
            radius_m=1000,
            limit=5,
        )

    with pytest.raises(ProviderError, match="daily request budget exhausted"):
        await guarded.search_nearby(
            category="cafe",
            latitude=58.01,
            longitude=56.25,
            radius_m=1000,
            limit=5,
        )

    assert provider.calls == 2
    status = await budget.status()
    assert status.used == 2
    assert status.limit == 2
    assert status.remaining == 0

    recreated = SQLiteDailyRequestBudget(
        database,
        provider="geoapify",
        daily_limit=2,
        clock=lambda: now,
    )
    await recreated.initialize()
    with pytest.raises(ProviderError, match="daily request budget exhausted"):
        await recreated.reserve()


@pytest.mark.asyncio
async def test_daily_budget_resets_on_next_utc_day(tmp_path) -> None:
    database = str(tmp_path / "permplaces.db")
    current = [datetime(2026, 10, 1, 23, 59, tzinfo=UTC)]
    budget = SQLiteDailyRequestBudget(
        database,
        provider="geoapify",
        daily_limit=1,
        clock=lambda: current[0],
    )
    await budget.initialize()

    first = await budget.reserve()
    assert first.day == "2026-10-01"
    assert first.remaining == 0

    current[0] = datetime(2026, 10, 2, 0, 1, tzinfo=UTC)
    second = await budget.reserve()

    assert second.day == "2026-10-02"
    assert second.used == 1


@pytest.mark.asyncio
async def test_budget_wrapper_exposes_underlying_capabilities(tmp_path) -> None:
    budget = SQLiteDailyRequestBudget(
        str(tmp_path / "permplaces.db"),
        provider="geoapify",
        daily_limit=10,
    )
    await budget.initialize()
    provider = FakeProvider()
    guarded = DailyBudgetPlacesProvider(provider, budget=budget)

    assert guarded.capabilities is provider.capabilities


def test_daily_budget_rejects_invalid_configuration(tmp_path) -> None:
    with pytest.raises(ValueError, match="daily_limit"):
        SQLiteDailyRequestBudget(
            str(tmp_path / "permplaces.db"),
            provider="geoapify",
            daily_limit=0,
        )

    with pytest.raises(ValueError, match="provider"):
        SQLiteDailyRequestBudget(
            str(tmp_path / "permplaces.db"),
            provider=" ",
            daily_limit=1,
        )
