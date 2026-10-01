from dataclasses import asdict
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.bot import (
    FavoriteNoteState,
    edit_favorite_note,
    favorite_note_text,
    remove_favorite_note,
)
from app.data import Venue
from app.notes import NotesRepository
from app.storage import FavoritesRepository


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


def venue() -> Venue:
    return Venue(
        id="osm:node/note-handler",
        name="Note handler",
        category="cafe",
        category_label="Кофейня",
        latitude=58.01,
        longitude=56.25,
        source="osm",
        source_id="node/note-handler",
    )


@pytest.mark.asyncio
async def test_note_text_handler_persists_and_updates_current_results(tmp_path) -> None:
    path = str(tmp_path / "permplaces.db")
    favorites = FavoritesRepository(path)
    notes = NotesRepository(path)
    item = venue()
    await favorites.initialize()
    assert await favorites.toggle(user_id=500, venue=item) is True

    state = FakeState(
        {
            "category": "favorites",
            "results": [asdict(item)],
            "note_venue_id": item.id,
        }
    )
    message = SimpleNamespace(
        from_user=SimpleNamespace(id=500),
        text="  Заказать раф без сиропа  ",
        answer=AsyncMock(),
    )

    await favorite_note_text(
        message,  # type: ignore[arg-type]
        state,  # type: ignore[arg-type]
        notes,
    )

    saved = await notes.get_for_venue(user_id=500, venue=item)
    assert saved is not None
    assert saved.text == "Заказать раф без сиропа"
    assert state.state is None
    assert state.data["note_venue_id"] is None
    result = state.data["results"][0]  # type: ignore[index]
    assert result["personal_note"] == "Заказать раф без сиропа"  # type: ignore[index]
    message.answer.assert_awaited_once()


@pytest.mark.asyncio
async def test_edit_note_handler_shows_existing_note_safely(tmp_path) -> None:
    path = str(tmp_path / "permplaces.db")
    favorites = FavoritesRepository(path)
    notes = NotesRepository(path)
    item = venue()
    await favorites.initialize()
    await favorites.toggle(user_id=501, venue=item)
    await notes.set_note(
        user_id=501,
        venue=item,
        text="<b>моя заметка</b>",
    )

    state = FakeState(
        {
            "category": "favorites",
            "results": [asdict(item)],
        }
    )
    answer_message = AsyncMock()
    callback = SimpleNamespace(
        data=f"favorite_note:edit:{item.id}",
        from_user=SimpleNamespace(id=501),
        answer=AsyncMock(),
        message=SimpleNamespace(answer=answer_message),
    )

    await edit_favorite_note(
        callback,  # type: ignore[arg-type]
        state,  # type: ignore[arg-type]
        notes,
    )

    assert state.state == FavoriteNoteState.awaiting_text
    assert state.data["note_venue_id"] == item.id
    rendered = answer_message.await_args.args[0]
    assert "&lt;b&gt;моя заметка&lt;/b&gt;" in rendered
    assert "<b>моя заметка</b>" not in rendered
    keyboard = answer_message.await_args.kwargs["reply_markup"]
    callbacks = [
        button.callback_data
        for row in keyboard.inline_keyboard
        for button in row
    ]
    assert f"favorite_note:remove:{item.id}" in callbacks


@pytest.mark.asyncio
async def test_remove_note_handler_clears_storage_and_result_state(tmp_path) -> None:
    path = str(tmp_path / "permplaces.db")
    favorites = FavoritesRepository(path)
    notes = NotesRepository(path)
    item = venue()
    await favorites.initialize()
    await favorites.toggle(user_id=502, venue=item)
    await notes.set_note(user_id=502, venue=item, text="Удалить")
    noted_item = (await notes.enrich_many(user_id=502, venues=[item]))[0]

    state = FakeState(
        {
            "category": "favorites",
            "results": [asdict(noted_item)],
            "note_venue_id": item.id,
        }
    )
    edit_text = AsyncMock()
    callback = SimpleNamespace(
        data=f"favorite_note:remove:{item.id}",
        from_user=SimpleNamespace(id=502),
        answer=AsyncMock(),
        message=SimpleNamespace(edit_text=edit_text),
    )

    await remove_favorite_note(
        callback,  # type: ignore[arg-type]
        state,  # type: ignore[arg-type]
        notes,
    )

    assert await notes.get_for_venue(user_id=502, venue=item) is None
    result = state.data["results"][0]  # type: ignore[index]
    assert result["personal_note"] is None  # type: ignore[index]
    assert state.state is None
    callback.answer.assert_awaited_once_with("Заметка удалена")
    edit_text.assert_awaited_once_with("📝 Заметка удалена.")
