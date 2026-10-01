from app.filters import PlaceFilters
from app.providers.capabilities import (
    FOURSQUARE_CAPABILITIES,
    GEOAPIFY_CAPABILITIES,
    OVERPASS_CAPABILITIES,
    TWOGIS_CAPABILITIES,
    ProviderCapabilities,
    ProviderStatus,
    provider_capabilities,
    render_provider_statuses,
)


def test_overpass_capabilities_cover_exact_district_and_fail_closed_filters() -> None:
    assert OVERPASS_CAPABILITIES.supports_area(
        category="breakfast",
        filters=PlaceFilters(
            outdoor_seating=True,
            wifi=True,
            open_now=True,
            family_friendly=True,
            open_late=True,
        ),
    )


def test_geoapify_only_routes_supported_nearby_queries() -> None:
    assert GEOAPIFY_CAPABILITIES.supports_nearby(
        category="cafe",
        filters=PlaceFilters(wifi=True),
    )
    assert not GEOAPIFY_CAPABILITIES.supports_nearby(category="breakfast")
    assert not GEOAPIFY_CAPABILITIES.supports_nearby(
        category="cafe",
        filters=PlaceFilters(open_now=True),
    )
    assert not GEOAPIFY_CAPABILITIES.supports_area(category="cafe")


def test_paid_provider_capabilities_preserve_known_filter_limits() -> None:
    assert TWOGIS_CAPABILITIES.supports_nearby(
        category="restaurant",
        filters=PlaceFilters(open_now=True),
    )
    assert not TWOGIS_CAPABILITIES.supports_nearby(
        category="restaurant",
        filters=PlaceFilters(open_now=True, open_late=True),
    )
    assert not FOURSQUARE_CAPABILITIES.supports_nearby(
        category="cafe",
        filters=PlaceFilters(family_friendly=True),
    )
    assert FOURSQUARE_CAPABILITIES.rating is True
    assert FOURSQUARE_CAPABILITIES.photos is True
    assert FOURSQUARE_CAPABILITIES.menu is True


def test_unknown_provider_is_routable_without_claiming_enrichment() -> None:
    class LegacyProvider:
        pass

    capabilities = provider_capabilities(LegacyProvider())

    assert capabilities.supports_nearby(
        category="custom",
        filters=PlaceFilters(family_friendly=True),
    )
    assert capabilities.supports_area(category="custom")
    assert capabilities.rating is False
    assert capabilities.photos is False


def test_provider_diagnostics_never_include_secret_material() -> None:
    statuses = (
        ProviderStatus(
            key="osm",
            label="OpenStreetMap / Overpass",
            enabled=True,
            capabilities=OVERPASS_CAPABILITIES,
        ),
        ProviderStatus(
            key="geoapify",
            label="Geoapify Places",
            enabled=False,
            capabilities=GEOAPIFY_CAPABILITIES,
            disabled_reason="GEOAPIFY_API_KEY не настроен",
        ),
    )

    rendered = render_provider_statuses(statuses)

    assert "OpenStreetMap / Overpass" in rendered
    assert "Geoapify Places" in rendered
    assert "GEOAPIFY_API_KEY не настроен" in rendered
    assert "секреты не выводятся" in rendered
    assert "apiKey=" not in rendered


def test_capabilities_can_reject_unsupported_combined_open_filters() -> None:
    capabilities = ProviderCapabilities(
        categories=frozenset({"cafe"}),
        nearby_search=True,
        open_now=True,
        open_late=True,
        combined_open_now_late=False,
    )

    assert capabilities.supports_nearby(
        category="cafe",
        filters=PlaceFilters(open_now=True),
    )
    assert not capabilities.supports_nearby(
        category="cafe",
        filters=PlaceFilters(open_now=True, open_late=True),
    )
