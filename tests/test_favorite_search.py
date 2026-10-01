from dataclasses import replace

from app.data import Venue
from app.favorite_search import (
    normalize_favorite_search_text,
    search_favorites,
)


def venue(
    source_id: str,
    name: str,
    *,
    address: str | None = None,
    note: str | None = None,
    tags: tuple[str, ...] = (),
    cuisine: tuple[str, ...] = (),
) -> Venue:
    return Venue(
        id=f"osm:{source_id}",
        name=name,
        category="cafe",
        category_label="Кофейня",
        latitude=58.01,
        longitude=56.25,
        source="osm",
        source_id=source_id,
        address=address,
        personal_note=note,
        personal_tags=tags,
        cuisine=cuisine,
    )


def test_normalization_is_casefolded_punctuation_safe_and_yo_insensitive() -> None:
    assert normalize_favorite_search_text("  Ёж-КОФЕ!!  ") == "еж кофе"


def test_search_prioritizes_exact_then_prefix_then_name_contains_then_other_fields() -> None:
    items = [
        venue("node/1", "Кофе на Ленина", address="Ленина 10"),
        venue("node/2", "Кофе", address="Пушкина 2"),
        venue("node/3", "Кофейня Кофе", address="Мира 1"),
        venue("node/4", "Совсем другое", note="кофе после работы"),
    ]

    result = search_favorites(items, "кофе")

    assert [item.source_id for item in result] == [
        "node/2",
        "node/1",
        "node/3",
        "node/4",
    ]


def test_search_requires_all_tokens_but_tokens_can_span_fields() -> None:
    items = [
        venue(
            "node/1",
            "Лампа",
            address="улица Ленина 15",
            note="тихо вечером",
        ),
        venue(
            "node/2",
            "Лампа 2",
            address="улица Ленина 20",
            note="шумно",
        ),
    ]

    result = search_favorites(items, "ленина тихо")

    assert [item.source_id for item in result] == ["node/1"]


def test_search_matches_user_tag_labels_without_treating_them_as_provider_facts() -> None:
    items = [
        replace(
            venue("node/1", "Первое"),
            personal_tags=("work",),
        ),
        replace(
            venue("node/2", "Второе"),
            personal_tags=("friends",),
        ),
    ]

    result = search_favorites(items, "для работы")

    assert [item.source_id for item in result] == ["node/1"]


def test_search_matches_cuisine_and_preserves_original_order_with_equal_rank() -> None:
    items = [
        venue("node/1", "Первое", cuisine=("coffee_shop", "dessert")),
        venue("node/2", "Второе", cuisine=("dessert",)),
    ]

    result = search_favorites(items, "dessert")

    assert [item.source_id for item in result] == ["node/1", "node/2"]


def test_empty_search_returns_no_results() -> None:
    assert search_favorites([venue("node/1", "Кофе")], "   ") == []
