from __future__ import annotations

import re
from dataclasses import dataclass

from app.districts import DISTRICT_BY_KEY, PERM_RELATION_ID
from app.filters import PlaceFilters


@dataclass(frozen=True, slots=True)
class SearchQueryPlan:
    updates: dict[str, object]
    requires_location: bool = False
    radius_ignored: bool = False

@dataclass(frozen=True, slots=True)
class ParsedSearchQuery:
    category: str | None
    outdoor_seating: bool | None = None
    wifi: bool | None = None
    radius_m: int | None = None
    district_key: str | None = None
    whole_city: bool = False
    nearby: bool = False

    @property
    def filters(self) -> PlaceFilters:
        return PlaceFilters(
            outdoor_seating=self.outdoor_seating is True,
            wifi=self.wifi is True,
        )


_CATEGORY_PATTERNS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("cafe", ("кофе", "кофейн", "кафе")),
    ("restaurant", ("ресторан", "поесть", "ужин", "обед")),
    ("bar", ("бар", "паб", "выпить")),
    ("pizza", ("пицц",)),
    ("sushi", ("суш", "ролл")),
    ("breakfast", ("завтрак", "позавтрак")),
    ("fastfood", ("фастфуд", "бургер")),
    ("dessert", ("десерт", "морожен", "кондитер")),
)

_DISTRICT_PATTERNS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("dzerzhinsky", ("дзержинск",)),
    ("industrialny", ("индустриальн",)),
    ("kirovsky", ("кировск",)),
    ("leninsky", ("ленинск",)),
    ("motovilikhinsky", ("мотовилихин",)),
    ("ordzhonikidzevsky", ("орджоникидзев",)),
    ("sverdlovsky", ("свердловск",)),
)

_WIFI_PATTERNS = ("wi-fi", "wifi", "вайфай", "вай-фай", "вай фай")
_WIFI_NEGATIVE_PATTERNS = ("без wi-fi", "без wifi", "без вайф", "без вай-фай", "без вай фай")
_TERRACE_PATTERNS = ("веранд", "террас", "летней площадк", "летняя площадк")
_TERRACE_NEGATIVE_PATTERNS = ("без веранд", "без террас", "без летней площад")
_WHOLE_CITY_PATTERNS = ("вся пермь", "по всей перми", "во всей перми")
_NEARBY_PATTERNS = ("рядом", "поблизости", "недалеко")

_RADIUS_RE = re.compile(
    r"(?P<value>\d+(?:[.,]\d+)?)\s*(?P<unit>км|километр(?:а|ов)?|м|метр(?:а|ов)?)\b",
    re.IGNORECASE,
)


def _contains_any(text: str, patterns: tuple[str, ...]) -> bool:
    return any(pattern in text for pattern in patterns)


def _feature_intent(
    text: str,
    *,
    positive: tuple[str, ...],
    negative: tuple[str, ...],
) -> bool | None:
    if _contains_any(text, negative):
        return False
    if _contains_any(text, positive):
        return True
    return None


def _parse_radius(text: str) -> int | None:
    match = _RADIUS_RE.search(text)
    if match is None:
        return None

    value = float(match.group("value").replace(",", "."))
    unit = match.group("unit").casefold()
    meters = round(value * 1000) if unit.startswith(("км", "километр")) else round(value)

    # Keep free-text Overpass searches bounded and useful.
    if not 100 <= meters <= 10_000:
        return None
    return meters


def parse_search_query(text: str) -> ParsedSearchQuery:
    normalized = " ".join(text.casefold().split())

    category = next(
        (
            category_name
            for category_name, patterns in _CATEGORY_PATTERNS
            if _contains_any(normalized, patterns)
        ),
        None,
    )
    district_key = next(
        (
            key
            for key, patterns in _DISTRICT_PATTERNS
            if _contains_any(normalized, patterns)
        ),
        None,
    )

    return ParsedSearchQuery(
        category=category,
        outdoor_seating=_feature_intent(
            normalized,
            positive=_TERRACE_PATTERNS,
            negative=_TERRACE_NEGATIVE_PATTERNS,
        ),
        wifi=_feature_intent(
            normalized,
            positive=_WIFI_PATTERNS,
            negative=_WIFI_NEGATIVE_PATTERNS,
        ),
        radius_m=_parse_radius(normalized),
        district_key=district_key,
        whole_city=_contains_any(normalized, _WHOLE_CITY_PATTERNS),
        nearby=_contains_any(normalized, _NEARBY_PATTERNS),
    )


def plan_search_query(
    parsed: ParsedSearchQuery,
    current: dict[str, object],
) -> SearchQueryPlan:
    updates: dict[str, object] = {}

    if parsed.outdoor_seating is not None:
        updates["filter_outdoor_seating"] = parsed.outdoor_seating
    if parsed.wifi is not None:
        updates["filter_wifi"] = parsed.wifi

    if parsed.district_key is not None:
        district = DISTRICT_BY_KEY[parsed.district_key]
        updates.update(
            search_scope="district",
            district_name=district.name,
            district_relation_id=district.relation_id,
        )
        return SearchQueryPlan(
            updates=updates,
            radius_ignored=parsed.radius_m is not None,
        )

    if parsed.whole_city:
        updates.update(
            search_scope="district",
            district_name="Вся Пермь",
            district_relation_id=PERM_RELATION_ID,
        )
        return SearchQueryPlan(
            updates=updates,
            radius_ignored=parsed.radius_m is not None,
        )

    if parsed.nearby or parsed.radius_m is not None:
        latitude = current.get("latitude")
        longitude = current.get("longitude")
        has_location = isinstance(latitude, (float, int)) and isinstance(
            longitude, (float, int)
        )

        if parsed.radius_m is not None:
            updates["radius_m"] = parsed.radius_m

        if not has_location:
            return SearchQueryPlan(
                updates=updates,
                requires_location=True,
            )

        updates["search_scope"] = "location"

    return SearchQueryPlan(updates=updates)
