import sqlite3

import pytest

from app.data import SourceRef, Venue
from app.notes import MAX_PERSONAL_NOTE_LENGTH, NotesRepository


def venue(
    *,
    source: str = "osm",
    source_id: str = "node/1",
    source_refs: tuple[SourceRef, ...] = (),
) -> Venue:
    return Venue(
        id=f"{source}:{source_id}",
        name="Note place",
        category="cafe",
        category_label="Кофейня",
        latitude=58.01,
        longitude=56.25,
        source=source,
        source_id=source_id,
        source_refs=source_refs,
    )


@pytest.mark.asyncio
async def test_notes_repository_sets_reads_and_normalizes_note(tmp_path) -> None:
    repository = NotesRepository(str(tmp_path / "permplaces.db"))
    await repository.initialize()
    item = venue()

    saved = await repository.set_note(
        user_id=1,
        venue=item,
        text="  Заказать фильтр-кофе  ",
    )
    restored = await repository.get_for_venue(user_id=1, venue=item)

    assert saved.text == "Заказать фильтр-кофе"
    assert restored == saved


@pytest.mark.asyncio
async def test_note_follows_provider_alias_and_edit_migrates_to_osm_key(
    tmp_path,
) -> None:
    path = str(tmp_path / "permplaces.db")
    repository = NotesRepository(path)
    await repository.initialize()

    geo = venue(source="geoapify", source_id="place-2")
    await repository.set_note(
        user_id=2,
        venue=geo,
        text="Старый Geoapify alias",
    )

    merged = venue(
        source="osm",
        source_id="node/2",
        source_refs=(
            SourceRef("osm", "node/2"),
            SourceRef("geoapify", "place-2"),
        ),
    )

    inherited = await repository.get_for_venue(user_id=2, venue=merged)
    assert inherited is not None
    assert inherited.text == "Старый Geoapify alias"

    await repository.set_note(
        user_id=2,
        venue=merged,
        text="Обновлено после merge",
    )

    with sqlite3.connect(path) as database:
        rows = database.execute(
            """
            SELECT identity_key, note
            FROM favorite_notes
            WHERE user_id = 2
            """
        ).fetchall()

    assert rows == [("osm:node/2", "Обновлено после merge")]


@pytest.mark.asyncio
async def test_remove_note_clears_all_known_aliases(tmp_path) -> None:
    path = str(tmp_path / "permplaces.db")
    repository = NotesRepository(path)
    await repository.initialize()

    geo = venue(source="geoapify", source_id="place-3")
    await repository.set_note(user_id=3, venue=geo, text="Удалить")

    merged = venue(
        source="osm",
        source_id="node/3",
        source_refs=(
            SourceRef("osm", "node/3"),
            SourceRef("geoapify", "place-3"),
        ),
    )

    assert await repository.remove_note(user_id=3, venue=merged) is True
    assert await repository.get_for_venue(user_id=3, venue=merged) is None
    assert await repository.remove_note(user_id=3, venue=merged) is False


@pytest.mark.asyncio
async def test_enrich_many_is_user_scoped_and_alias_aware(tmp_path) -> None:
    path = str(tmp_path / "permplaces.db")
    repository = NotesRepository(path)
    await repository.initialize()

    first = venue(source="geoapify", source_id="place-4")
    second = venue(source="osm", source_id="node/5")
    await repository.set_note(user_id=4, venue=first, text="Моя")
    await repository.set_note(user_id=5, venue=second, text="Чужая")

    merged_first = venue(
        source="osm",
        source_id="node/4",
        source_refs=(
            SourceRef("osm", "node/4"),
            SourceRef("geoapify", "place-4"),
        ),
    )
    enriched = await repository.enrich_many(
        user_id=4,
        venues=[merged_first, second],
    )

    assert enriched[0].personal_note == "Моя"
    assert enriched[1].personal_note is None


@pytest.mark.asyncio
async def test_notes_repository_rejects_blank_and_too_long_notes(tmp_path) -> None:
    repository = NotesRepository(str(tmp_path / "permplaces.db"))
    await repository.initialize()
    item = venue()

    with pytest.raises(ValueError, match="must not be empty"):
        await repository.set_note(user_id=1, venue=item, text="   ")

    with pytest.raises(ValueError, match="at most"):
        await repository.set_note(
            user_id=1,
            venue=item,
            text="x" * (MAX_PERSONAL_NOTE_LENGTH + 1),
        )
