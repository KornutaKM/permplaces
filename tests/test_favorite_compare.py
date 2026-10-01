from app.data import Venue
from app.favorite_compare import (
    MAX_COMPARE_OPTIONS,
    favorite_compare_options,
    favorite_from_compare_token,
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


def test_compare_options_exclude_primary_and_preserve_favorite_order() -> None:
    first = venue("node/1", "Первое")
    second = venue("node/2", "Второе")
    third = venue("node/3", "Третье")

    options = favorite_compare_options(
        [first, second, third],
        primary_id=second.id,
    )

    assert [option.venue.id for option in options] == [first.id, third.id]
    assert all(len(option.token) == 20 for option in options)


def test_compare_token_resolves_only_current_unique_option() -> None:
    primary = venue("node/1", "Первое")
    second = venue("node/2", "Второе")
    options = favorite_compare_options(
        [primary, second],
        primary_id=primary.id,
    )

    assert favorite_from_compare_token(options, options[0].token) == second
    assert favorite_from_compare_token(options, "stale") is None


def test_compare_options_are_bounded() -> None:
    primary = venue("node/0", "Первое")
    others = [
        venue(f"node/{index}", f"Place {index}")
        for index in range(1, MAX_COMPARE_OPTIONS + 8)
    ]

    options = favorite_compare_options(
        [primary, *others],
        primary_id=primary.id,
        limit=1000,
    )

    assert len(options) == MAX_COMPARE_OPTIONS
    assert options[-1].venue.id == f"osm:node/{MAX_COMPARE_OPTIONS}"


def test_compare_options_limit_is_at_least_one() -> None:
    primary = venue("node/0", "Первое")
    second = venue("node/1", "Второе")

    options = favorite_compare_options(
        [primary, second],
        primary_id=primary.id,
        limit=0,
    )

    assert [option.venue.id for option in options] == [second.id]
