from app.data import find_venues
from app.ui import render_venue_card


def test_find_venues_by_category() -> None:
    venues = find_venues(category="cafe")

    assert len(venues) == 1
    assert venues[0].category == "cafe"


def test_find_venues_by_tag() -> None:
    venues = find_venues(query="wifi")

    assert len(venues) == 1
    assert venues[0].name == "Демо-кофейня"


def test_demo_card_is_explicitly_marked_as_demo() -> None:
    venue = find_venues(category="restaurant")[0]

    card = render_venue_card(venue)

    assert "демонстрационная карточка" in card
    assert "Рейтинг появится после подключения провайдера" in card
