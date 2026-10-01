from dataclasses import asdict, replace
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.bot import (
    FavoriteSearchState,
    favorite_search_clear,
    favorite_search_start,
    favorite_search_text,
)
from app.data import Venue


class FakeState:
    def __init__(self, data: dict[str, object]) -> None:
        self.data = dict(data)
        self.state: object | None = None

    async def get_data(self) -> dict[str, object]:
        return dict(self.data)

    async def update_data(self, **kwargs: object) -> None:
        self.data.update(kwargs)

    async def set_state(self, value: object | None) -> None:
        self.state = value


def venue(source_id: str, name: str) -> Venue:
    return Venue(
        id=f"osm:{source_id}",
        name=name,
        category="cafe",
        category_label="Кофейня",
        latitude=58.01,
        longitude=56.25,
        source="osm",
        source_id=source_id,
    )


@pytest.mark.asyncio
async def test_favorite_search_start_is_available_only_for_favorites() -> None:
    item = venue("node/1", "Первое")
    state = FakeState(
        {
            "category": "favorites",
            "favorite_all_results": [asdict(item)],
            "results": [asdict(item)],
        }
    )
    answer_message = AsyncMock()
    callback = SimpleNamespace(
        answer=AsyncMock(),
        message=SimpleNamespace(answer=answer_message),
    )

    await favorite_search_start(
        callback,  # type: ignore[arg-type]
        state,  # type: ignore[arg-type]
    )

    assert state.state == FavoriteSearchState.awaiting_query
    rendered = answer_message.await_args.args[0]
    assert "Поиск в избранном" in rendered
    keyboard = answer_message.await_args.kwargs["reply_markup"]
    assert keyboard.inline_keyboard[0][0].callback_data == "fs:cancel"


@pytest.mark.asyncio
async def test_favorite_search_text_searches_name_note_and_tags_locally() -> None:
    first = replace(
        venue("node/1", "Тихая чашка"),
        personal_note="брать ноутбук",
        personal_tags=("work",),
    )
    second = venue("node/2", "Громкое место")
    all_results = [asdict(first), asdict(second)]
    state = FakeState(
        {
            "category": "favorites",
            "favorite_all_results": all_results,
            "results": all_results,
            "favorite_filter": "friends",
            "favorite_search_query": None,
            "favorite_category_filter": "cafe",
            "favorite_district_filter": "Ленинский",
            "favorite_district_missing": False,
            "result_index": 0,
        }
    )
    answer = AsyncMock()
    message = SimpleNamespace(
        text="для работы",
        answer=answer,
    )

    await favorite_search_text(
        message,  # type: ignore[arg-type]
        state,  # type: ignore[arg-type]
    )

    assert state.state is None
    assert state.data["favorite_filter"] is None
    assert state.data["favorite_search_query"] == "для работы"
    assert state.data["favorite_category_filter"] is None
    assert state.data["favorite_district_filter"] is None
    assert state.data["favorite_district_missing"] is False
    assert len(state.data["results"]) == 1  # type: ignore[arg-type]
    assert state.data["results"][0]["id"] == first.id  # type: ignore[index]
    rendered = answer.await_args.args[0]
    assert "Поиск в избранном" in rendered
    keyboard = answer.await_args.kwargs["reply_markup"]
    callbacks = [
        button.callback_data
        for row in keyboard.inline_keyboard
        for button in row
    ]
    assert "fs:clear" in callbacks


@pytest.mark.asyncio
async def test_favorite_search_no_match_keeps_editor_open_for_retry() -> None:
    item = venue("node/1", "Кофе")
    state = FakeState(
        {
            "category": "favorites",
            "favorite_all_results": [asdict(item)],
            "results": [asdict(item)],
        }
    )
    await state.set_state(FavoriteSearchState.awaiting_query)
    answer = AsyncMock()
    message = SimpleNamespace(
        text="не существует",
        answer=answer,
    )

    await favorite_search_text(
        message,  # type: ignore[arg-type]
        state,  # type: ignore[arg-type]
    )

    assert state.state == FavoriteSearchState.awaiting_query
    assert "Ничего не найдено" in answer.await_args.args[0]


@pytest.mark.asyncio
async def test_favorite_search_clear_restores_all_results_and_resets_local_views() -> None:
    first = venue("node/1", "Первое")
    second = venue("node/2", "Второе")
    all_results = [asdict(first), asdict(second)]
    state = FakeState(
        {
            "category": "favorites",
            "favorite_all_results": all_results,
            "results": [asdict(second)],
            "favorite_filter": None,
            "favorite_search_query": "второе",
            "favorite_category_filter": "cafe",
            "favorite_district_filter": None,
            "favorite_district_missing": False,
            "result_index": 0,
            "result_scenario": None,
        }
    )
    edit_text = AsyncMock()
    callback = SimpleNamespace(
        answer=AsyncMock(),
        message=SimpleNamespace(edit_text=edit_text),
    )

    await favorite_search_clear(
        callback,  # type: ignore[arg-type]
        state,  # type: ignore[arg-type]
    )

    assert state.data["favorite_search_query"] is None
    assert state.data["favorite_filter"] is None
    assert state.data["favorite_category_filter"] is None
    assert state.data["favorite_district_filter"] is None
    assert state.data["favorite_district_missing"] is False
    assert len(state.data["results"]) == 2  # type: ignore[arg-type]
    callback.answer.assert_awaited_once_with("Поиск сброшен")
    edit_text.assert_awaited_once()



@pytest.mark.asyncio
async def test_favorite_search_clear_restores_selected_sort() -> None:
    first = venue("node/1", "Яблоко")
    second = venue("node/2", "Альфа")
    all_results = [asdict(first), asdict(second)]
    state = FakeState(
        {
            "category": "favorites",
            "favorite_all_results": all_results,
            "results": [asdict(first)],
            "favorite_filter": None,
            "favorite_search_query": "яблоко",
            "favorite_sort": "name",
            "result_index": 0,
            "result_scenario": None,
        }
    )
    callback = SimpleNamespace(
        answer=AsyncMock(),
        message=SimpleNamespace(edit_text=AsyncMock()),
    )

    await favorite_search_clear(
        callback,  # type: ignore[arg-type]
        state,  # type: ignore[arg-type]
    )

    assert [
        item["id"] for item in state.data["results"]  # type: ignore[index]
    ] == [second.id, first.id]
    assert state.data["favorite_sort"] == "name"
