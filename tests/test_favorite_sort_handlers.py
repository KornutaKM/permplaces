from dataclasses import asdict, replace
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.bot import favorite_sort_menu, favorite_sort_selected
from app.data import Venue


class FakeState:
    def __init__(self, data: dict[str, object]) -> None:
        self.data = dict(data)

    async def get_data(self) -> dict[str, object]:
        return dict(self.data)

    async def update_data(self, **kwargs: object) -> None:
        self.data.update(kwargs)


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
async def test_sort_menu_marks_current_sort() -> None:
    first = venue("node/1", "B")
    state = FakeState(
        {
            "category": "favorites",
            "favorite_all_results": [asdict(first)],
            "results": [asdict(first)],
            "favorite_sort": "name",
        }
    )
    edit_reply_markup = AsyncMock()
    callback = SimpleNamespace(
        answer=AsyncMock(),
        message=SimpleNamespace(
            edit_reply_markup=edit_reply_markup,
            answer=AsyncMock(),
        ),
    )

    await favorite_sort_menu(
        callback,  # type: ignore[arg-type]
        state,  # type: ignore[arg-type]
    )

    keyboard = edit_reply_markup.await_args.kwargs["reply_markup"]
    labels = [
        button.text
        for row in keyboard.inline_keyboard
        for button in row
    ]
    assert "✅ 🔤 По названию" in labels


@pytest.mark.asyncio
async def test_sort_selection_orders_current_tag_filter_and_clears_search() -> None:
    first = replace(venue("node/1", "Яблоко"), personal_tags=("work",))
    second = replace(venue("node/2", "Альфа"), personal_tags=("work",))
    third = replace(venue("node/3", "Бета"), personal_tags=("friends",))
    all_results = [asdict(first), asdict(second), asdict(third)]
    state = FakeState(
        {
            "category": "favorites",
            "favorite_all_results": all_results,
            "results": [asdict(first)],
            "favorite_filter": "work",
            "favorite_search_query": "яблоко",
            "favorite_sort": "recent",
            "result_index": 0,
            "result_scenario": None,
        }
    )
    edit_text = AsyncMock()
    callback = SimpleNamespace(
        data="fso:name",
        answer=AsyncMock(),
        message=SimpleNamespace(edit_text=edit_text),
    )

    await favorite_sort_selected(
        callback,  # type: ignore[arg-type]
        state,  # type: ignore[arg-type]
    )

    assert state.data["favorite_search_query"] is None
    assert state.data["favorite_filter"] == "work"
    assert state.data["favorite_sort"] == "name"
    assert [
        item["id"] for item in state.data["results"]  # type: ignore[index]
    ] == [second.id, first.id]
    callback.answer.assert_awaited_once_with("Сортировка: 🔤 По названию")
    edit_text.assert_awaited_once()


@pytest.mark.asyncio
async def test_sort_by_notes_is_local_and_preserves_unmatched_favorites_in_all_results() -> None:
    first = venue("node/1", "Первое")
    second = replace(venue("node/2", "Второе"), personal_note="важно")
    all_results = [asdict(first), asdict(second)]
    state = FakeState(
        {
            "category": "favorites",
            "favorite_all_results": all_results,
            "results": all_results,
            "favorite_filter": None,
            "favorite_search_query": None,
            "favorite_sort": "recent",
            "result_index": 0,
            "result_scenario": None,
        }
    )
    callback = SimpleNamespace(
        data="fso:notes",
        answer=AsyncMock(),
        message=SimpleNamespace(edit_text=AsyncMock()),
    )

    await favorite_sort_selected(
        callback,  # type: ignore[arg-type]
        state,  # type: ignore[arg-type]
    )

    assert [
        item["id"] for item in state.data["results"]  # type: ignore[index]
    ] == [second.id, first.id]
    assert [
        item["id"] for item in state.data["favorite_all_results"]  # type: ignore[index]
    ] == [first.id, second.id]
