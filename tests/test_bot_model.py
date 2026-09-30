from dataclasses import asdict

from app.bot import _venue_from_dict
from app.data import FieldSource, PhotoRef, SourceRef, Venue


def test_bot_state_restores_nested_provider_objects() -> None:
    venue = Venue(
        id="osm:node/visual",
        name="Visual",
        category="cafe",
        category_label="Кофейня",
        latitude=58.01,
        longitude=56.25,
        source="osm",
        source_id="node/visual",
        source_refs=(
            SourceRef("osm", "node/visual"),
            SourceRef("foursquare", "fsq-visual"),
        ),
        field_sources=(
            FieldSource("name", "osm", "node/visual"),
            FieldSource("photos", "foursquare", "fsq-visual"),
        ),
        photos=(
            PhotoRef(
                provider="foursquare",
                source_id="photo-visual",
                url="https://images.example.test/original/visual.jpg",
                attribution="Powered by Foursquare",
            ),
        ),
        cuisine=("coffee_shop",),
    )

    restored = _venue_from_dict(asdict(venue))

    assert restored == venue
    assert restored.source_refs[1].provider == "foursquare"
    assert restored.field_sources[1].field_name == "photos"
    assert restored.photos[0].source_id == "photo-visual"
