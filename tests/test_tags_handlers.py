from dataclasses import asdict, replace
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.bot import (
    favorite_filter_menu,
    favorite_filter_selected,
    favorite_tag_toggle,
)
from app.data import Venue
from app.storage import FavoritesRepository
from app.tags import FavoriteTagsRepository


class FakeState:
    def __init__(self, data: dict[str, object]) -> None:
        self.data = dict(data)

    async def get_data(self) -> dict[str, object]:
        return dict(self.data)

    async def update_data(self, **kwargs: object) -> None:
        self.data.update(kwargs)


def venue(source_id: str) -> Venue:
    return Venue(
        id=f"osm:{source_id}",
        name=f"Tagged {source_id}",
        category="cafe",
        category_label="Кофейня",
        latitude=58.01,
        longitude=56.25,
        source="osm",
        source_id=source_id,
    )


@pytest.mark.asyncio
async def test_tag_toggle_updates_storage_and_all_favorite_state(tmp_path) -> None:
    path = str(tmp_path / "permplaces.db")
    favorites = FavoritesRepository(path)
    tags = FavoriteTagsRepository(path)
    item = venue("node/toggle")
    await favorites.initialize()
    await favorites.toggle(user_id=700, venue=item)

    raw = asdict(item)
    state = FakeState(
        {
            "category": "favorites",
            "results": [raw],
            "favorite_all_results": [raw],
            "favorite_filter": None,
            "result_index": 0,
        }
    )
    callback = SimpleNamespace(
        data=f"ft:want:{item.id}",
        from_user=SimpleNamespace(id=700),
        answer=AsyncMock(),
        message=SimpleNamespace(edit_reply_markup=AsyncMock()),
    )

    await favorite_tag_toggle(
        callback,  # type: ignore[arg-type]
        state,  # type: ignore[arg-type]
        tags,
    )

    assert await tags.tags_for_venue(user_id=700, venue=item) == ("want",)
    assert state.data["results"][0]["personal_tags"] == ("want",)  # type: ignore[index]
    assert state.data["favorite_all_results"][0]["personal_tags"] == ("want",)  # type: ignore[index]
    callback.message.edit_reply_markup.assert_awaited_once()


@pytest.mark.asyncio
async def test_removing_last_active_tag_clears_filter_instead_of_emptying_state(
    tmp_path,
) -> None:
    path = str(tmp_path / "permplaces.db")
    favorites = FavoritesRepository(path)
    tags = FavoriteTagsRepository(path)
    item = venue("node/active-filter")
    await favorites.initialize()
    await favorites.toggle(user_id=701, venue=item)
    await tags.toggle_tag(user_id=701, venue=item, tag="want")
    tagged = replace(item, personal_tags=("want",))
    raw = asdict(tagged)
    state = FakeState(
        {
            "category": "favorites",
            "results": [raw],
            "favorite_all_results": [raw],
            "favorite_filter": "want",
            "result_index": 0,
        }
    )
    callback = SimpleNamespace(
        data=f"ft:want:{item.id}",
        from_user=SimpleNamespace(id=701),
        answer=AsyncMock(),
        message=SimpleNamespace(edit_reply_markup=AsyncMock()),
    )

    await favorite_tag_toggle(
        callback,  # type: ignore[arg-type]
        state,  # type: ignore[arg-type]
        tags,
    )

    assert state.data["favorite_filter"] is None
    assert len(state.data["results"]) == 1  # type: ignore[arg-type]
    assert state.data["results"][0]["personal_tags"] == ()  # type: ignore[index]


@pytest.mark.asyncio
async def test_filter_menu_uses_all_favorites_and_tag_counts() -> None:
    first = replace(venue("node/1"), personal_tags=("want", "work"))
    second = replace(venue("node/2"), personal_tags=("want",))
    state = FakeState(
        {
            "category": "favorites",
            "results": [asdict(first), asdict(second)],
            "favorite_all_results": [asdict(first), asdict(second)],
            "favorite_filter": None,
            "result_index": 0,
        }
    )
    edit_reply_markup = AsyncMock()
    callback = SimpleNamespace(
        data="ff:menu",
        answer=AsyncMock(),
        message=SimpleNamespace(edit_reply_markup=edit_reply_markup),
    )

    await favorite_filter_menu(
        callback,  # type: ignore[arg-type]
        state,  # type: ignore[arg-type]
    )

    keyboard = edit_reply_markup.await_args.kwargs["reply_markup"]
    labels = [
        button.text
        for row in keyboard.inline_keyboard
        for button in row
    ]
    assert "📌 Хочу сходить (2)" in labels
    assert "💻 Для работы (1)" in labels


@pytest.mark.asyncio
async def test_filter_selection_replaces_visible_results_without_losing_all() -> None:
    first = replace(venue("node/1"), personal_tags=("friends",))
    second = replace(venue("node/2"), personal_tags=("work",))
    all_results = [asdict(first), asdict(second)]
    state = FakeState(
        {
            "category": "favorites",
            "results": all_results,
            "favorite_all_results": all_results,
            "favorite_filter": None,
            "result_index": 0,
            "result_scenario": None,
        }
    )
    edit_text = AsyncMock()
    callback = SimpleNamespace(
        data="ff:work",
        answer=AsyncMock(),
        message=SimpleNamespace(edit_text=edit_text),
    )

    await favorite_filter_selected(
        callback,  # type: ignore[arg-type]
        state,  # type: ignore[arg-type]
    )

    assert state.data["favorite_filter"] == "work"
    assert len(state.data["favorite_all_results"]) == 2  # type: ignore[arg-type]
    assert len(state.data["results"]) == 1  # type: ignore[arg-type]
    assert state.data["results"][0]["id"] == second.id  # type: ignore[index]
    edit_text.assert_awaited_once()
