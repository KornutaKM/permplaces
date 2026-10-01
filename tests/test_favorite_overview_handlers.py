from dataclasses import asdict, replace
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.bot import favorite_overview
from app.data import Venue


class FakeState:
    def __init__(self, data: dict[str, object]) -> None:
        self.data = dict(data)

    async def get_data(self) -> dict[str, object]:
        return dict(self.data)


def venue(source_id: str, name: str, *, district: str | None = None) -> Venue:
    return Venue(
        id=f"osm:{source_id}",
        name=name,
        category="cafe",
        category_label="Кофейня",
        latitude=58.01,
        longitude=56.25,
        source="osm",
        source_id=source_id,
        district=district,
    )


@pytest.mark.asyncio
async def test_favorite_overview_uses_all_results_not_current_filtered_view() -> None:
    first = replace(
        venue("node/1", "Первое", district="Ленинский"),
        personal_note="заметка",
        personal_tags=("want",),
    )
    second = replace(
        venue("node/2", "Второе"),
        personal_tags=("friends",),
    )
    state = FakeState(
        {
            "category": "favorites",
            "favorite_all_results": [asdict(first), asdict(second)],
            "results": [asdict(first)],
            "favorite_filter": "want",
            "favorite_sort": "name",
        }
    )
    edit_text = AsyncMock()
    callback = SimpleNamespace(
        answer=AsyncMock(),
        message=SimpleNamespace(
            edit_text=edit_text,
            answer=AsyncMock(),
        ),
    )

    await favorite_overview(
        callback,  # type: ignore[arg-type]
        state,  # type: ignore[arg-type]
    )

    rendered = edit_text.await_args.args[0]
    assert "Сохранено мест: <b>2</b>" in rendered
    assert "С личной заметкой: <b>1</b>" in rendered
    assert "С личными метками: <b>2</b>" in rendered
    keyboard = edit_text.await_args.kwargs["reply_markup"]
    labels = [
        button.text
        for row in keyboard.inline_keyboard
        for button in row
    ]
    assert "↕️ Сортировка: 🔤 По названию" in labels
    assert "← К результатам" in labels


@pytest.mark.asyncio
async def test_favorite_overview_rejects_non_favorite_state() -> None:
    state = FakeState(
        {
            "category": "cafe",
            "results": [asdict(venue("node/1", "Первое"))],
        }
    )
    answer_message = AsyncMock()
    callback = SimpleNamespace(
        answer=AsyncMock(),
        message=SimpleNamespace(
            edit_text=AsyncMock(),
            answer=answer_message,
        ),
    )

    await favorite_overview(
        callback,  # type: ignore[arg-type]
        state,  # type: ignore[arg-type]
    )

    answer_message.assert_awaited_once()
    assert "актуального списка избранного" in answer_message.await_args.args[0]


@pytest.mark.asyncio
async def test_favorite_overview_handles_empty_stale_favorites() -> None:
    state = FakeState(
        {
            "category": "favorites",
            "favorite_all_results": [],
            "results": [],
        }
    )
    edit_text = AsyncMock()
    callback = SimpleNamespace(
        answer=AsyncMock(),
        message=SimpleNamespace(
            edit_text=edit_text,
            answer=AsyncMock(),
        ),
    )

    await favorite_overview(
        callback,  # type: ignore[arg-type]
        state,  # type: ignore[arg-type]
    )

    assert "Избранное пока пусто" in edit_text.await_args.args[0]
