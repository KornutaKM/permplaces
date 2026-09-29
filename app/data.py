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
    is_open_now: bool | None = None
    is_open_late: bool | None = None
    phone: str | None = None
    website: str | None = None
    cuisine: tuple[str, ...] = ()
    outdoor_seating: bool | None = None
    wifi: bool | None = None
    kids_area: bool | None = None
    highchair: bool | None = None
    changing_table: bool | None = None
    price_label: str | None = None
    rating: float | None = None
    review_count: int | None = None
