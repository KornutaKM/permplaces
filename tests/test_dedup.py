from app.data import Venue
from app.dedup import ensure_provenance, merge_provider_results, merge_venues, same_venue


def venue(
    *,
    source: str,
    source_id: str,
    name: str = "Кофейня Север",
    latitude: float = 58.0100,
    longitude: float = 56.2500,
    address: str | None = None,
    phone: str | None = None,
    website: str | None = None,
    rating: float | None = None,
    rating_scale: float | None = None,
    review_count: int | None = None,
) -> Venue:
    return Venue(
        id=f"{source}:{source_id}",
        name=name,
        category="cafe",
        category_label="Кофейня",
        latitude=latitude,
        longitude=longitude,
        source=source,
        source_id=source_id,
        address=address,
        phone=phone,
        website=website,
        rating=rating,
        rating_scale=rating_scale,
        review_count=review_count,
    )


def test_same_source_identity_always_matches() -> None:
    first = venue(source="osm", source_id="node/1", latitude=58.01)
    second = venue(source="osm", source_id="node/1", latitude=59.00)

    assert same_venue(first, second) is True


def test_exact_name_nearby_matches_across_providers() -> None:
    osm = venue(source="osm", source_id="node/1")
    catalog = venue(
        source="catalog",
        source_id="abc",
        name="КОФЕЙНЯ   СЕВЕР",
        latitude=58.0102,
        longitude=56.2501,
    )

    assert same_venue(osm, catalog) is True


def test_same_chain_name_farther_away_stays_distinct() -> None:
    first = venue(source="osm", source_id="node/1")
    branch = venue(
        source="catalog",
        source_id="branch-2",
        latitude=58.0120,
        longitude=56.2500,
    )

    assert same_venue(first, branch) is False


def test_matching_phone_is_strong_identity_signal() -> None:
    first = venue(
        source="osm",
        source_id="node/1",
        name="Север",
        phone="+7 (342) 200-00-00",
    )
    second = venue(
        source="catalog",
        source_id="abc",
        name="Sever Coffee",
        phone="8 342 200 00 00",
        latitude=58.011,
    )

    assert same_venue(first, second) is True


def test_merge_keeps_primary_facts_and_fills_missing_secondary_facts() -> None:
    primary = venue(
        source="osm",
        source_id="node/1",
        address="ул. Ленина, 10",
    )
    secondary = venue(
        source="catalog",
        source_id="abc",
        address="другой адрес не должен перезаписать",
        phone="+7 342 200-00-00",
        rating=4.8,
        review_count=125,
    )

    merged = merge_venues(primary, secondary)

    assert merged.id == primary.id
    assert merged.address == "ул. Ленина, 10"
    assert merged.phone == "+7 342 200-00-00"
    assert merged.rating == 4.8
    assert merged.review_count == 125
    assert [(ref.provider, ref.source_id) for ref in merged.source_refs] == [
        ("osm", "node/1"),
        ("catalog", "abc"),
    ]
    phone_source = next(
        item for item in merged.field_sources if item.field_name == "phone"
    )
    assert phone_source.provider == "catalog"


def test_rating_and_review_count_are_never_mixed_between_providers() -> None:
    primary = venue(
        source="osm",
        source_id="node/1",
        rating=4.5,
        review_count=None,
    )
    secondary = venue(
        source="catalog",
        source_id="abc",
        rating=4.9,
        review_count=500,
    )

    merged = merge_venues(primary, secondary)

    assert merged.rating == 4.5
    assert merged.review_count is None


def test_merge_provider_results_preserves_provider_priority() -> None:
    primary = venue(source="osm", source_id="node/1", address="OSM address")
    duplicate = venue(
        source="catalog",
        source_id="abc",
        address="Catalog address",
        phone="+7 342 200-00-00",
    )
    other = venue(
        source="catalog",
        source_id="def",
        name="Другая кофейня",
        latitude=58.02,
    )

    results = merge_provider_results(
        [[primary], [duplicate, other]],
        limit=10,
    )

    assert len(results) == 2
    assert results[0].id == primary.id
    assert results[0].address == "OSM address"
    assert results[0].phone == "+7 342 200-00-00"


def test_single_provider_result_gets_explicit_provenance() -> None:
    item = ensure_provenance(venue(source="osm", source_id="node/1"))

    assert item.source_refs[0].provider == "osm"
    assert any(
        source.field_name == "name" and source.provider == "osm"
        for source in item.field_sources
    )


def test_rating_scale_is_kept_with_secondary_rating_source() -> None:
    primary = venue(source="osm", source_id="node/1")
    secondary = venue(
        source="foursquare",
        source_id="fsq-1",
        rating=8.9,
        rating_scale=10.0,
        review_count=480,
    )

    merged = merge_venues(primary, secondary)

    assert merged.rating == 8.9
    assert merged.rating_scale == 10.0
    assert merged.review_count == 480
    assert {
        item.field_name: item.provider for item in merged.field_sources
    }["rating_scale"] == "foursquare"
