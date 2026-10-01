from __future__ import annotations

from dataclasses import dataclass

from app.filters import PlaceFilters

ALL_PLACE_CATEGORIES = frozenset(
    {
        "restaurant",
        "cafe",
        "bar",
        "fastfood",
        "pizza",
        "sushi",
        "breakfast",
        "dessert",
        "food_drink",
    }
)


@dataclass(frozen=True, slots=True)
class ProviderCapabilities:
    """Static, conservative contract for one places provider.

    A capability is true only when the adapter can prove the requested signal.
    Unknown providers use a compatibility contract so test doubles and third-party
    adapters are not silently skipped by the composite layer.
    """

    categories: frozenset[str] | None = None
    nearby_search: bool = False
    district_search: bool = False
    outdoor_seating: bool = False
    wifi: bool = False
    open_now: bool = False
    open_late: bool = False
    family_friendly: bool = False
    combined_open_now_late: bool = False
    opening_hours: bool = False
    rating: bool = False
    reviews: bool = False
    photos: bool = False
    menu: bool = False

    def supports_category(self, category: str) -> bool:
        return self.categories is None or category in self.categories

    def supports_filters(self, filters: PlaceFilters | None) -> bool:
        active = filters or PlaceFilters()
        if active.outdoor_seating and not self.outdoor_seating:
            return False
        if active.wifi and not self.wifi:
            return False
        if active.open_now and not self.open_now:
            return False
        if active.open_late and not self.open_late:
            return False
        if active.family_friendly and not self.family_friendly:
            return False
        if (
            active.open_now
            and active.open_late
            and not self.combined_open_now_late
        ):
            return False
        return True

    def supports_nearby(
        self,
        *,
        category: str,
        filters: PlaceFilters | None = None,
    ) -> bool:
        return (
            self.nearby_search
            and self.supports_category(category)
            and self.supports_filters(filters)
        )

    def supports_area(
        self,
        *,
        category: str,
        filters: PlaceFilters | None = None,
    ) -> bool:
        return (
            self.district_search
            and self.supports_category(category)
            and self.supports_filters(filters)
        )


# Compatibility fallback for legacy/test providers that do not publish a
# capability contract yet. It is deliberately permissive for routing only;
# it does not claim enrichment fields such as rating/photos/menu.
UNKNOWN_PROVIDER_CAPABILITIES = ProviderCapabilities(
    categories=None,
    nearby_search=True,
    district_search=True,
    outdoor_seating=True,
    wifi=True,
    open_now=True,
    open_late=True,
    family_friendly=True,
    combined_open_now_late=True,
)


OVERPASS_CAPABILITIES = ProviderCapabilities(
    categories=ALL_PLACE_CATEGORIES,
    nearby_search=True,
    district_search=True,
    outdoor_seating=True,
    wifi=True,
    open_now=True,
    open_late=True,
    family_friendly=True,
    combined_open_now_late=True,
    opening_hours=True,
)

GEOAPIFY_CAPABILITIES = ProviderCapabilities(
    categories=frozenset(
        {
            "restaurant",
            "cafe",
            "bar",
            "fastfood",
            "pizza",
            "sushi",
            "dessert",
            "food_drink",
        }
    ),
    nearby_search=True,
    wifi=True,
)

TWOGIS_CAPABILITIES = ProviderCapabilities(
    categories=frozenset(
        {
            "restaurant",
            "cafe",
            "bar",
            "fastfood",
            "pizza",
            "sushi",
            "breakfast",
            "dessert",
        }
    ),
    nearby_search=True,
    open_now=True,
    open_late=True,
    combined_open_now_late=False,
)

FOURSQUARE_CAPABILITIES = ProviderCapabilities(
    categories=frozenset(
        {
            "restaurant",
            "cafe",
            "bar",
            "fastfood",
            "pizza",
            "sushi",
            "breakfast",
            "dessert",
        }
    ),
    nearby_search=True,
    outdoor_seating=True,
    wifi=True,
    open_now=True,
    open_late=True,
    combined_open_now_late=False,
    opening_hours=True,
    rating=True,
    reviews=True,
    photos=True,
    menu=True,
)


def provider_capabilities(provider: object) -> ProviderCapabilities:
    capabilities = getattr(provider, "capabilities", None)
    if isinstance(capabilities, ProviderCapabilities):
        return capabilities
    return UNKNOWN_PROVIDER_CAPABILITIES


@dataclass(frozen=True, slots=True)
class ProviderStatus:
    key: str
    label: str
    enabled: bool
    capabilities: ProviderCapabilities
    disabled_reason: str | None = None


def _capability_labels(capabilities: ProviderCapabilities) -> tuple[str, ...]:
    labels: list[str] = []
    if capabilities.nearby_search:
        labels.append("рядом")
    if capabilities.district_search:
        labels.append("районы OSM")
    if capabilities.wifi:
        labels.append("Wi-Fi")
    if capabilities.opening_hours:
        labels.append("часы работы")
    if capabilities.open_now:
        labels.append("открыто сейчас")
    if capabilities.open_late:
        labels.append("открыто в 23:00")
    if capabilities.family_friendly:
        labels.append("для детей")
    if capabilities.rating:
        labels.append("рейтинг")
    if capabilities.photos:
        labels.append("фото")
    if capabilities.menu:
        labels.append("меню")
    return tuple(labels)


def render_provider_statuses(statuses: tuple[ProviderStatus, ...]) -> str:
    lines = ["<b>Источники PermPlaces</b>"]
    for status in statuses:
        prefix = "✅" if status.enabled else "○"
        lines.append("")
        lines.append(f"{prefix} <b>{status.label}</b>")
        if status.enabled:
            labels = _capability_labels(status.capabilities)
            lines.append("  " + (", ".join(labels) if labels else "базовый поиск"))
        elif status.disabled_reason:
            lines.append(f"  {status.disabled_reason}")
    lines.extend(
        [
            "",
            "<i>Диагностика показывает только возможности адаптеров; "
            "ключи и другие секреты не выводятся.</i>",
        ]
    )
    return "\n".join(lines)
