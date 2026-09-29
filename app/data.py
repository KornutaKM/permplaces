from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Venue:
    id: str
    name: str
    category: str
    category_label: str
    district: str
    address: str
    price_label: str
    rating: float | None
    review_count: int | None
    open_until: str | None
    tags: tuple[str, ...]


# Temporary UI fixtures only. They are intentionally marked as demo data and must never
# be presented as verified facts about real Perm businesses.
DEMO_VENUES: tuple[Venue, ...] = (
    Venue(
        id="demo-cafe-1",
        name="Демо-кофейня",
        category="cafe",
        category_label="Кофейня",
        district="Ленинский",
        address="Пермь · демо-адрес",
        price_label="₽₽",
        rating=None,
        review_count=None,
        open_until=None,
        tags=("кофе", "завтрак", "wifi"),
    ),
    Venue(
        id="demo-restaurant-1",
        name="Демо-ресторан",
        category="restaurant",
        category_label="Ресторан",
        district="Свердловский",
        address="Пермь · демо-адрес",
        price_label="₽₽",
        rating=None,
        review_count=None,
        open_until=None,
        tags=("ужин", "семья", "десерты"),
    ),
    Venue(
        id="demo-bar-1",
        name="Демо-бар",
        category="bar",
        category_label="Бар",
        district="Мотовилихинский",
        address="Пермь · демо-адрес",
        price_label="₽₽",
        rating=None,
        review_count=None,
        open_until=None,
        tags=("вечер", "бар"),
    ),
)


def find_venues(*, category: str | None = None, query: str | None = None) -> list[Venue]:
    venues = list(DEMO_VENUES)
    if category:
        venues = [venue for venue in venues if venue.category == category]
    if query:
        needle = query.casefold().strip()
        venues = [
            venue
            for venue in venues
            if needle in venue.name.casefold()
            or any(needle in tag.casefold() for tag in venue.tags)
        ]
    return venues
