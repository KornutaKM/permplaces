from dataclasses import replace

from app.data import Venue
from app.favorite_sort import (
    DEFAULT_FAVORITE_SORT,
    FAVORITE_SORT_LABELS,
    sort_favorites,
)


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


def test_recent_sort_preserves_repository_order() -> None:
    items = [
        venue("node/3", "Третье"),
        venue("node/2", "Второе"),
        venue("node/1", "Первое"),
    ]

    assert sort_favorites(items, DEFAULT_FAVORITE_SORT) == items


def test_name_sort_is_normalized_and_stable() -> None:
    items = [
        venue("node/1", "Ёж кофе"),
        venue("node/2", "альфа"),
        venue("node/3", "ЕЖ-КОФЕ"),
    ]

    result = sort_favorites(items, "name")

    assert [item.source_id for item in result] == [
        "node/2",
        "node/1",
        "node/3",
    ]


def test_notes_sort_puts_nonempty_personal_notes_first_stably() -> None:
    items = [
        venue("node/1", "Без заметки"),
        replace(venue("node/2", "С заметкой"), personal_note="вернуться"),
        replace(venue("node/3", "Пробелы"), personal_note="   "),
        replace(venue("node/4", "Ещё заметка"), personal_note="заказать чай"),
    ]

    result = sort_favorites(items, "notes")

    assert [item.source_id for item in result] == [
        "node/2",
        "node/4",
        "node/1",
        "node/3",
    ]


def test_tags_sort_uses_only_known_unique_personal_tags() -> None:
    items = [
        replace(venue("node/1", "Одна"), personal_tags=("want",)),
        replace(
            venue("node/2", "Две"),
            personal_tags=("work", "friends", "friends", "unknown"),
        ),
        venue("node/3", "Ноль"),
    ]

    result = sort_favorites(items, "tags")

    assert [item.source_id for item in result] == [
        "node/2",
        "node/1",
        "node/3",
    ]


def test_unknown_sort_key_falls_back_to_recent() -> None:
    items = [venue("node/2", "B"), venue("node/1", "A")]

    assert sort_favorites(items, "unsupported") == items
    assert DEFAULT_FAVORITE_SORT in FAVORITE_SORT_LABELS
