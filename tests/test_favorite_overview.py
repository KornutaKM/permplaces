from dataclasses import replace

from app.data import Venue
from app.favorite_overview import (
    build_favorite_overview,
    render_favorite_overview,
)


def venue(
    source_id: str,
    *,
    category_label: str = "Кофейня",
    district: str | None = None,
) -> Venue:
    return Venue(
        id=f"osm:{source_id}",
        name=f"Place {source_id}",
        category="cafe",
        category_label=category_label,
        latitude=58.01,
        longitude=56.25,
        source="osm",
        source_id=source_id,
        district=district,
    )


def test_overview_counts_notes_tags_categories_and_missing_district() -> None:
    items = [
        replace(
            venue("node/1", district="Ленинский"),
            personal_note="вернуться",
            personal_tags=("want", "work"),
        ),
        replace(
            venue("node/2", category_label="Ресторан", district="Ленинский"),
            personal_tags=("want", "unknown"),
        ),
        venue("node/3", category_label="Ресторан"),
    ]

    overview = build_favorite_overview(items)

    assert overview.total == 3
    assert overview.with_notes == 1
    assert overview.with_tags == 2
    assert overview.tag_counts == (("want", 2), ("work", 1))
    assert overview.categories == (("Ресторан", 2), ("Кофейня", 1))
    assert overview.districts == (("Ленинский", 2),)
    assert overview.missing_district == 1


def test_overview_count_ranking_is_deterministic_and_bounded() -> None:
    items = [
        venue("node/1", category_label="Бета", district="Б"),
        venue("node/2", category_label="Альфа", district="А"),
        venue("node/3", category_label="Бета", district="Б"),
        venue("node/4", category_label="Альфа", district="А"),
        venue("node/5", category_label="Гамма", district="Г"),
    ]

    overview = build_favorite_overview(items, limit=2)

    assert overview.categories == (("Альфа", 2), ("Бета", 2))
    assert overview.districts == (("А", 2), ("Б", 2))


def test_overview_ignores_blank_note_unknown_tags_and_blank_district() -> None:
    item = replace(
        venue("node/1", district="   "),
        personal_note="   ",
        personal_tags=("custom",),
    )

    overview = build_favorite_overview([item])

    assert overview.with_notes == 0
    assert overview.with_tags == 0
    assert overview.tag_counts == ()
    assert overview.missing_district == 1


def test_render_overview_escapes_provider_text_and_explains_local_scope() -> None:
    overview = build_favorite_overview(
        [
            venue(
                "node/1",
                category_label="<b>Unsafe</b>",
                district="Ленинский <район>",
            )
        ]
    )

    rendered = render_favorite_overview(overview)

    assert "&lt;b&gt;Unsafe&lt;/b&gt;" in rendered
    assert "Ленинский &lt;район&gt;" in rendered
    assert "<b>Unsafe</b>" not in rendered
    assert "не запрашивает внешние каталоги" in rendered
