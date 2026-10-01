from dataclasses import asdict, replace
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.bot import (
    favorite_category_facet_selected,
    favorite_cuisine_facet_selected,
    favorite_district_facet_selected,
    favorite_facets_menu,
    favorite_facets_reset,
)
from app.data import Venue
from app.favorite_facets import build_favorite_facets


class FakeState:
    def __init__(self, data: dict[str, object]) -> None:
        self.data = dict(data)

    async def get_data(self) -> dict[str, object]:
        return dict(self.data)

    async def update_data(self, **kwargs: object) -> None:
        self.data.update(kwargs)


def venue(
    source_id: str,
    *,
    category: str = "cafe",
    category_label: str = "Кофейня",
    district: str | None = None,
    cuisine: tuple[str, ...] = (),
) -> Venue:
    return Venue(
        id=f"osm:{source_id}",
        name=f"Place {source_id}",
        category=category,
        category_label=category_label,
        latitude=58.01,
        longitude=56.25,
        source="osm",
        source_id=source_id,
        district=district,
        cuisine=cuisine,
    )


def callback(data: str) -> SimpleNamespace:
    return SimpleNamespace(
        data=data,
        answer=AsyncMock(),
        message=SimpleNamespace(
            edit_text=AsyncMock(),
            edit_reply_markup=AsyncMock(),
            answer=AsyncMock(),
        ),
    )


@pytest.mark.asyncio
async def test_facets_menu_uses_full_loaded_favorites() -> None:
    first = venue(
        "node/1",
        district="Ленинский",
        cuisine=("coffee_shop",),
    )
    second = venue(
        "node/2",
        category="restaurant",
        category_label="Ресторан",
        district="Мотовилихинский",
    )
    all_results = [asdict(first), asdict(second)]
    state = FakeState(
        {
            "category": "favorites",
            "favorite_all_results": all_results,
            "results": [asdict(first)],
            "favorite_category_filter": "cafe",
            "favorite_district_filter": None,
            "favorite_district_missing": False,
            "favorite_cuisine_filter": "coffee_shop",
            "favorite_cuisine_missing": False,
        }
    )
    cb = callback("fx:menu")

    await favorite_facets_menu(
        cb,  # type: ignore[arg-type]
        state,  # type: ignore[arg-type]
    )

    keyboard = cb.message.edit_reply_markup.await_args.kwargs["reply_markup"]
    labels = [
        button.text
        for row in keyboard.inline_keyboard
        for button in row
    ]
    assert "🍽 Категория: Кофейня" in labels
    assert "🏙 Район: все" in labels
    assert "🍜 Кухня: coffee_shop" in labels


@pytest.mark.asyncio
async def test_category_facet_composes_with_tag_and_clears_search() -> None:
    first = replace(
        venue("node/1", category="cafe", category_label="Кофейня"),
        personal_tags=("work",),
    )
    second = replace(
        venue("node/2", category="restaurant", category_label="Ресторан"),
        personal_tags=("work",),
    )
    third = replace(
        venue("node/3", category="restaurant", category_label="Ресторан"),
        personal_tags=("friends",),
    )
    all_venues = [first, second, third]
    all_results = [asdict(item) for item in all_venues]
    facets = build_favorite_facets(all_venues)
    restaurant = next(item for item in facets.categories if item.value == "restaurant")
    state = FakeState(
        {
            "category": "favorites",
            "favorite_all_results": all_results,
            "results": [asdict(first)],
            "favorite_filter": "work",
            "favorite_search_query": "place",
            "favorite_category_filter": None,
            "favorite_district_filter": None,
            "favorite_district_missing": False,
            "favorite_cuisine_filter": None,
            "favorite_cuisine_missing": False,
            "favorite_sort": "recent",
            "result_index": 0,
            "result_scenario": None,
        }
    )
    cb = callback(f"fx:c:{restaurant.token}")

    await favorite_category_facet_selected(
        cb,  # type: ignore[arg-type]
        state,  # type: ignore[arg-type]
    )

    assert state.data["favorite_category_filter"] == "restaurant"
    assert state.data["favorite_search_query"] is None
    assert state.data["favorite_filter"] == "work"
    assert [
        item["id"] for item in state.data["results"]  # type: ignore[index]
    ] == [second.id]
    cb.message.edit_text.assert_awaited_once()


@pytest.mark.asyncio
async def test_missing_district_facet_selects_only_cards_without_district() -> None:
    missing = venue("node/1")
    known = venue("node/2", district="Ленинский")
    all_venues = [missing, known]
    state = FakeState(
        {
            "category": "favorites",
            "favorite_all_results": [asdict(item) for item in all_venues],
            "results": [asdict(item) for item in all_venues],
            "favorite_filter": None,
            "favorite_search_query": None,
            "favorite_category_filter": None,
            "favorite_district_filter": None,
            "favorite_district_missing": False,
            "favorite_cuisine_filter": None,
            "favorite_cuisine_missing": False,
            "favorite_sort": "recent",
            "result_index": 0,
            "result_scenario": None,
        }
    )
    cb = callback("fx:d:missing")

    await favorite_district_facet_selected(
        cb,  # type: ignore[arg-type]
        state,  # type: ignore[arg-type]
    )

    assert state.data["favorite_district_missing"] is True
    assert state.data["favorite_district_filter"] is None
    assert [
        item["id"] for item in state.data["results"]  # type: ignore[index]
    ] == [missing.id]


@pytest.mark.asyncio
async def test_cuisine_facet_composes_with_category_and_uses_saved_values() -> None:
    first = venue(
        "node/1",
        category="restaurant",
        category_label="Ресторан",
        cuisine=("Italian", "pizza"),
    )
    second = venue(
        "node/2",
        category="restaurant",
        category_label="Ресторан",
        cuisine=("sushi",),
    )
    third = venue(
        "node/3",
        category="cafe",
        category_label="Кофейня",
        cuisine=("italian",),
    )
    all_venues = [first, second, third]
    facets = build_favorite_facets(all_venues)
    italian = next(item for item in facets.cuisines if item.value == "italian")
    state = FakeState(
        {
            "category": "favorites",
            "favorite_all_results": [asdict(item) for item in all_venues],
            "results": [asdict(item) for item in all_venues],
            "favorite_filter": None,
            "favorite_search_query": "italian",
            "favorite_category_filter": "restaurant",
            "favorite_district_filter": None,
            "favorite_district_missing": False,
            "favorite_cuisine_filter": None,
            "favorite_cuisine_missing": False,
            "favorite_sort": "recent",
            "result_index": 0,
            "result_scenario": None,
        }
    )
    cb = callback(f"fx:u:{italian.token}")

    await favorite_cuisine_facet_selected(
        cb,  # type: ignore[arg-type]
        state,  # type: ignore[arg-type]
    )

    assert state.data["favorite_cuisine_filter"] == "italian"
    assert state.data["favorite_cuisine_missing"] is False
    assert state.data["favorite_search_query"] is None
    assert [
        item["id"] for item in state.data["results"]  # type: ignore[index]
    ] == [first.id]


@pytest.mark.asyncio
async def test_missing_cuisine_facet_selects_only_unknown_saved_cuisine() -> None:
    missing = venue("node/1")
    known = venue("node/2", cuisine=("coffee_shop",))
    state = FakeState(
        {
            "category": "favorites",
            "favorite_all_results": [asdict(missing), asdict(known)],
            "results": [asdict(missing), asdict(known)],
            "favorite_filter": None,
            "favorite_search_query": None,
            "favorite_category_filter": None,
            "favorite_district_filter": None,
            "favorite_district_missing": False,
            "favorite_cuisine_filter": None,
            "favorite_cuisine_missing": False,
            "favorite_sort": "recent",
            "result_index": 0,
            "result_scenario": None,
        }
    )
    cb = callback("fx:u:missing")

    await favorite_cuisine_facet_selected(
        cb,  # type: ignore[arg-type]
        state,  # type: ignore[arg-type]
    )

    assert state.data["favorite_cuisine_missing"] is True
    assert state.data["favorite_cuisine_filter"] is None
    assert [
        item["id"] for item in state.data["results"]  # type: ignore[index]
    ] == [missing.id]


@pytest.mark.asyncio
async def test_facets_reset_preserves_tag_filter_and_sort() -> None:
    first = replace(
        venue(
            "node/1",
            category="cafe",
            category_label="Кофейня",
            cuisine=("coffee_shop",),
        ),
        personal_tags=("want",),
    )
    second = replace(
        venue("node/2", category="restaurant", category_label="Ресторан"),
        personal_tags=("want",),
    )
    all_results = [asdict(first), asdict(second)]
    state = FakeState(
        {
            "category": "favorites",
            "favorite_all_results": all_results,
            "results": [asdict(first)],
            "favorite_filter": "want",
            "favorite_search_query": None,
            "favorite_category_filter": "cafe",
            "favorite_district_filter": None,
            "favorite_district_missing": False,
            "favorite_cuisine_filter": "coffee_shop",
            "favorite_cuisine_missing": False,
            "favorite_sort": "name",
            "result_index": 0,
            "result_scenario": None,
        }
    )
    cb = callback("fx:reset")

    await favorite_facets_reset(
        cb,  # type: ignore[arg-type]
        state,  # type: ignore[arg-type]
    )

    assert state.data["favorite_category_filter"] is None
    assert state.data["favorite_district_filter"] is None
    assert state.data["favorite_district_missing"] is False
    assert state.data["favorite_cuisine_filter"] is None
    assert state.data["favorite_cuisine_missing"] is False
    assert state.data["favorite_filter"] == "want"
    assert state.data["favorite_sort"] == "name"
    assert len(state.data["results"]) == 2  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_stale_facet_token_fails_without_changing_view() -> None:
    item = venue("node/1")
    raw = asdict(item)
    state = FakeState(
        {
            "category": "favorites",
            "favorite_all_results": [raw],
            "results": [raw],
            "favorite_category_filter": None,
        }
    )
    cb = callback("fx:u:stale")

    await favorite_cuisine_facet_selected(
        cb,  # type: ignore[arg-type]
        state,  # type: ignore[arg-type]
    )

    cb.answer.assert_awaited_once_with(
        "Этот фильтр устарел. Откройте меню снова."
    )
    assert state.data["results"] == [raw]
