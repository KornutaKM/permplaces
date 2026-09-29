from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Venue:
    id: str
    name: str
    category: str
    category_label: str
    latitude: float
    longitude: float
    source: str
    source_id: str
    source_url: str | None = None
    address: str | None = None
    district: str | None = None
    distance_m: int | None = None
    opening_hours: str | None = None
    phone: str | None = None
    website: str | None = None
    cuisine: tuple[str, ...] = ()
    price_label: str | None = None
    rating: float | None = None
    review_count: int | None = None
