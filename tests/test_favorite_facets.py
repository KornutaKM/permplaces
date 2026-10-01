from app.data import Venue
from app.favorite_facets import (
    MAX_FACET_OPTIONS,
    build_favorite_facets,
    category_from_token,
    district_from_token,
    filter_favorites_by_facets,
)


def venue(
    source_id: str,
    *,
    category: str = "cafe",
    category_label: str = "Кофейня",
    district: str | None = None,
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
    )


def test_build_facets_counts_and_ranks_categories_and_districts() -> None:
    items = [
        venue("node/1", district="Ленинский"),
        venue(
            "node/2",
            category="restaurant",
            category_label="Ресторан",
            district="Ленинский",
        ),
        venue(
            "node/3",
            category="restaurant",
            category_label="Ресторан",
            district="Мотовилихинский",
        ),
        venue("node/4"),
    ]

    facets = build_favorite_facets(items)

    assert [(item.value, item.count) for item in facets.categories] == [
        ("cafe", 2),
        ("restaurant", 2),
    ]
    assert [(item.value, item.count) for item in facets.districts] == [
        ("Ленинский", 2),
        ("Мотовилихинский", 1),
    ]
    assert facets.missing_district == 1


def test_facet_tokens_resolve_only_current_unique_options() -> None:
    facets = build_favorite_facets(
        [
            venue("node/1", district="Ленинский"),
            venue(
                "node/2",
                category="restaurant",
                category_label="Ресторан",
                district="Мотовилихинский",
            ),
        ]
    )

    category = facets.categories[0]
    district = facets.districts[0]

    assert category_from_token(facets, category.token) == category.value
    assert district_from_token(facets, district.token) == district.value
    assert category_from_token(facets, "stale") is None
    assert district_from_token(facets, "stale") is None


def test_filter_facets_composes_category_and_district() -> None:
    items = [
        venue("node/1", district="Ленинский"),
        venue(
            "node/2",
            category="restaurant",
            category_label="Ресторан",
            district="Ленинский",
        ),
        venue(
            "node/3",
            category="restaurant",
            category_label="Ресторан",
            district="Мотовилихинский",
        ),
    ]

    result = filter_favorites_by_facets(
        items,
        category="restaurant",
        district="Ленинский",
        district_missing=False,
    )

    assert [item.source_id for item in result] == ["node/2"]


def test_missing_district_filter_is_exact_and_does_not_infer() -> None:
    items = [
        venue("node/1"),
        venue("node/2", district="   "),
        venue("node/3", district="Ленинский"),
    ]

    result = filter_favorites_by_facets(
        items,
        category=None,
        district=None,
        district_missing=True,
    )

    assert [item.source_id for item in result] == ["node/1", "node/2"]


def test_facets_are_bounded_deterministically() -> None:
    items = [
        venue(
            f"node/{index}",
            district=f"Район {index:02d}",
        )
        for index in range(MAX_FACET_OPTIONS + 5)
    ]

    facets = build_favorite_facets(items)

    assert len(facets.districts) == MAX_FACET_OPTIONS
    assert facets.districts[0].label == "Район 00"
    assert facets.districts[-1].label == f"Район {MAX_FACET_OPTIONS - 1:02d}"
