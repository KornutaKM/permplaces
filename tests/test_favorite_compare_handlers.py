from dataclasses import asdict
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.bot import (
    favorite_compare_choose,
    favorite_compare_selected,
    favorite_compare_start,
)
from app.data import Venue
from app.favorite_compare import favorite_compare_options


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
async def test_compare_start_uses_current_visible_favorite_as_primary() -> None:
    first = venue("node/1", "Первое")
    second = venue("node/2", "Второе")
    third = venue("node/3", "Третье")
    state = FakeState(
        {
            "category": "favorites",
            "favorite_all_results": [
                asdict(first),
                asdict(second),
                asdict(third),
            ],
            "results": [asdict(second), asdict(third)],
            "result_index": 0,
        }
    )
    cb = callback("fcmp:start")

    await favorite_compare_start(
        cb,  # type: ignore[arg-type]
        state,  # type: ignore[arg-type]
    )

    assert state.data["favorite_compare_primary_id"] == second.id
    keyboard = cb.message.edit_reply_markup.await_args.kwargs["reply_markup"]
    labels = [
        button.text
        for row in keyboard.inline_keyboard
        for button in row
    ]
    assert "Первое" in labels
    assert "Третье" in labels
    assert "Второе" not in labels


@pytest.mark.asyncio
async def test_compare_selected_renders_two_saved_favorites() -> None:
    first = venue("node/1", "Первое")
    second = venue("node/2", "Второе")
    venues = [first, second]
    options = favorite_compare_options(
        venues,
        primary_id=first.id,
    )
    state = FakeState(
        {
            "category": "favorites",
            "favorite_all_results": [asdict(item) for item in venues],
            "results": [asdict(first), asdict(second)],
            "result_index": 0,
            "favorite_compare_primary_id": first.id,
        }
    )
    cb = callback(f"fcmp:pick:{options[0].token}")

    await favorite_compare_selected(
        cb,  # type: ignore[arg-type]
        state,  # type: ignore[arg-type]
    )

    cb.answer.assert_awaited_once_with("Сравнение готово")
    rendered = cb.message.edit_text.await_args.args[0]
    assert "Сравнение избранного" in rendered
    assert "1. Первое" in rendered
    assert "2. Второе" in rendered
    keyboard = cb.message.edit_text.await_args.kwargs["reply_markup"]
    callbacks = [
        button.callback_data
        for row in keyboard.inline_keyboard
        for button in row
    ]
    assert callbacks == ["fcmp:choose", "results:current"]


@pytest.mark.asyncio
async def test_compare_choose_reuses_stored_primary() -> None:
    first = venue("node/1", "Первое")
    second = venue("node/2", "Второе")
    state = FakeState(
        {
            "category": "favorites",
            "favorite_all_results": [asdict(first), asdict(second)],
            "results": [asdict(second)],
            "result_index": 0,
            "favorite_compare_primary_id": first.id,
        }
    )
    cb = callback("fcmp:choose")

    await favorite_compare_choose(
        cb,  # type: ignore[arg-type]
        state,  # type: ignore[arg-type]
    )

    keyboard = cb.message.edit_reply_markup.await_args.kwargs["reply_markup"]
    labels = [
        button.text
        for row in keyboard.inline_keyboard
        for button in row
    ]
    assert "Второе" in labels
    assert "Первое" not in labels


@pytest.mark.asyncio
async def test_compare_stale_token_fails_closed() -> None:
    first = venue("node/1", "Первое")
    second = venue("node/2", "Второе")
    state = FakeState(
        {
            "category": "favorites",
            "favorite_all_results": [asdict(first), asdict(second)],
            "results": [asdict(first)],
            "result_index": 0,
            "favorite_compare_primary_id": first.id,
        }
    )
    cb = callback("fcmp:pick:stale")

    await favorite_compare_selected(
        cb,  # type: ignore[arg-type]
        state,  # type: ignore[arg-type]
    )

    cb.answer.assert_awaited_once_with(
        "Этот вариант сравнения устарел. Откройте список снова."
    )
    cb.message.edit_text.assert_not_awaited()


@pytest.mark.asyncio
async def test_compare_requires_two_favorites() -> None:
    first = venue("node/1", "Первое")
    state = FakeState(
        {
            "category": "favorites",
            "favorite_all_results": [asdict(first)],
            "results": [asdict(first)],
            "result_index": 0,
        }
    )
    cb = callback("fcmp:start")

    await favorite_compare_start(
        cb,  # type: ignore[arg-type]
        state,  # type: ignore[arg-type]
    )

    cb.message.answer.assert_awaited_once_with(
        "Для сравнения нужны как минимум два актуальных избранных места."
    )
