from app.data import SourceRef, Venue
from app.identity import canonical_venue_key, venue_identity_keys


def venue(
    *,
    source: str,
    source_id: str,
    source_refs: tuple[SourceRef, ...] = (),
) -> Venue:
    return Venue(
        id=f"{source}:{source_id}",
        name="Identity",
        category="cafe",
        category_label="Кофейня",
        latitude=58.01,
        longitude=56.25,
        source=source,
        source_id=source_id,
        source_refs=source_refs,
    )


def test_identity_keys_include_primary_and_all_unique_aliases() -> None:
    item = venue(
        source="geoapify",
        source_id="place-1",
        source_refs=(
            SourceRef("geoapify", "place-1"),
            SourceRef("osm", "node/1"),
            SourceRef("osm", "node/1"),
        ),
    )

    assert venue_identity_keys(item) == (
        "geoapify:place-1",
        "osm:node/1",
    )


def test_canonical_identity_prefers_osm_alias() -> None:
    item = venue(
        source="geoapify",
        source_id="place-2",
        source_refs=(
            SourceRef("geoapify", "place-2"),
            SourceRef("osm", "node/2"),
        ),
    )

    assert canonical_venue_key(item) == "osm:node/2"


def test_canonical_identity_falls_back_to_primary_provider() -> None:
    item = venue(
        source="geoapify",
        source_id="place-3",
        source_refs=(SourceRef("geoapify", "place-3"),),
    )

    assert canonical_venue_key(item) == "geoapify:place-3"


def test_primary_osm_identity_stays_canonical_without_source_refs() -> None:
    item = venue(source="osm", source_id="way/9")

    assert canonical_venue_key(item) == "osm:way/9"
    assert venue_identity_keys(item) == ("osm:way/9",)
