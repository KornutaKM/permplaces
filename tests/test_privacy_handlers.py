from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.bot import (
    delete_my_data_confirmed,
    export_my_data,
    my_data,
    provider_diagnostics,
)
from app.data import Venue
from app.privacy import UserDataRepository
from app.providers.budget import DailyBudgetStatus
from app.providers.capabilities import (
    GEOAPIFY_CAPABILITIES,
    ProviderStatus,
)
from app.ratings import RatingsRepository
from app.storage import FavoritesRepository


class FakeBudget:
    async def status(self) -> DailyBudgetStatus:
        return DailyBudgetStatus(
            provider="geoapify",
            day="2026-10-01",
            used=25,
            limit=2500,
        )


def venue() -> Venue:
    return Venue(
        id="osm:node/privacy-handler",
        name="Privacy handler",
        category="cafe",
        category_label="Кофейня",
        latitude=58.01,
        longitude=56.25,
        source="osm",
        source_id="node/privacy-handler",
    )


@pytest.mark.asyncio
async def test_provider_diagnostics_include_live_budget_without_secrets() -> None:
    answer = AsyncMock()
    message = SimpleNamespace(answer=answer)

    await provider_diagnostics(
        message,
        (
            ProviderStatus(
                key="geoapify",
                label="Geoapify Places",
                enabled=True,
                capabilities=GEOAPIFY_CAPABILITIES,
            ),
        ),
        {"geoapify": FakeBudget()},  # type: ignore[arg-type]
    )

    rendered = answer.await_args.args[0]
    assert "25/2500" in rendered
    assert "осталось 2475" in rendered
    assert "apiKey" not in rendered


@pytest.mark.asyncio
async def test_mydata_reports_only_current_user_counts(tmp_path) -> None:
    path = str(tmp_path / "permplaces.db")
    favorites = FavoritesRepository(path)
    ratings = RatingsRepository(path)
    repository = UserDataRepository(path)
    await repository.initialize()

    await favorites.toggle(user_id=100, venue=venue())
    await favorites.toggle(user_id=200, venue=venue())
    await ratings.set_rating(user_id=100, venue=venue(), score=5)
    await ratings.set_rating(user_id=200, venue=venue(), score=1)

    answer = AsyncMock()
    message = SimpleNamespace(
        from_user=SimpleNamespace(id=100),
        answer=answer,
    )

    await my_data(message, repository)

    rendered = answer.await_args.args[0]
    assert "Избранное: <b>1</b>" in rendered
    assert "Мои оценки: <b>1</b>" in rendered
    assert "100" not in rendered
    assert "200" not in rendered
    assert answer.await_args.kwargs["reply_markup"] is not None


@pytest.mark.asyncio
async def test_confirmed_privacy_delete_clears_persistent_and_session_data(
    tmp_path,
) -> None:
    path = str(tmp_path / "permplaces.db")
    favorites = FavoritesRepository(path)
    ratings = RatingsRepository(path)
    repository = UserDataRepository(path)
    await repository.initialize()

    await favorites.toggle(user_id=300, venue=venue())
    await ratings.set_rating(user_id=300, venue=venue(), score=4)

    edit_text = AsyncMock()
    answer_callback = AsyncMock()
    callback = SimpleNamespace(
        from_user=SimpleNamespace(id=300),
        answer=answer_callback,
        message=SimpleNamespace(edit_text=edit_text),
    )
    state = SimpleNamespace(clear=AsyncMock())

    await delete_my_data_confirmed(
        callback,  # type: ignore[arg-type]
        state,  # type: ignore[arg-type]
        repository,
    )

    summary = await repository.summary_for_user(user_id=300)
    assert summary.total_rows == 0
    state.clear.assert_awaited_once()
    answer_callback.assert_awaited_once_with("Данные удалены")
    rendered = edit_text.await_args.args[0]
    assert "Удалено избранных мест: <b>1</b>" in rendered
    assert "Удалено оценок: <b>1</b>" in rendered



@pytest.mark.asyncio
async def test_privacy_export_handler_sends_json_document_for_current_user(
    tmp_path,
) -> None:
    path = str(tmp_path / "permplaces.db")
    favorites = FavoritesRepository(path)
    ratings = RatingsRepository(path)
    repository = UserDataRepository(path)
    await repository.initialize()

    await favorites.toggle(user_id=400, venue=venue())
    await ratings.set_rating(user_id=400, venue=venue(), score=5)

    answer_document = AsyncMock()
    answer_callback = AsyncMock()
    callback = SimpleNamespace(
        from_user=SimpleNamespace(id=400),
        answer=answer_callback,
        message=SimpleNamespace(answer_document=answer_document),
    )

    await export_my_data(
        callback,  # type: ignore[arg-type]
        repository,
    )

    answer_callback.assert_awaited_once_with("Готовлю экспорт…")
    answer_document.assert_awaited_once()
    document = answer_document.await_args.args[0]
    assert document.filename == "permplaces-mydata.json"

    caption = answer_document.await_args.kwargs["caption"]
    assert "Избранное: 1" in caption
    assert "Оценки: 1" in caption
    assert "400" not in caption
