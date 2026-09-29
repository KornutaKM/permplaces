import pytest

from app.data import Venue
from app.surprise import choose_surprise


def _venue(identifier: str) -> Venue:
    return Venue(
        id=identifier,
        name=identifier,
        category="food_drink",
        category_label="Заведение",
        latitude=58.01,
        longitude=56.25,
        source="osm",
        source_id=f"node/{identifier}",
    )


def test_surprise_uses_supplied_random_index() -> None:
    venues = [_venue("a"), _venue("b"), _venue("c")]

    index, selected = choose_surprise(venues, choose_index=lambda count: count - 1)

    assert index == 2
    assert selected.id == "c"


def test_surprise_rejects_empty_candidates() -> None:
    with pytest.raises(ValueError, match="empty"):
        choose_surprise([])


def test_surprise_rejects_invalid_random_index() -> None:
    with pytest.raises(ValueError, match="out-of-range"):
        choose_surprise([_venue("a")], choose_index=lambda _count: 3)
