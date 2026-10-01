from dataclasses import replace

import pytest

from app.data import SourceRef, Venue
from app.ratings import (
    RatingsRepository,
    canonical_rating_key,
    venue_rating_keys,
)


def venue(
    *,
    source: str = "osm",
    source_id: str = "node/1",
    source_refs: tuple[SourceRef, ...] = (),
) -> Venue:
    return Venue(
        id=f"{source}:{source_id}",
        name="Rating place",
        category="cafe",
        category_label="Кофейня",
        latitude=58.01,
        longitude=56.25,
        source=source,
        source_id=source_id,
        source_refs=source_refs,
    )


def test_rating_keys_include_all_provider_aliases_and_prefer_osm_canonical() -> None:
    item = venue(
        source="geoapify",
        source_id="place-1",
        source_refs=(
            SourceRef("geoapify", "place-1"),
            SourceRef("osm", "node/1"),
        ),
    )

    assert venue_rating_keys(item) == (
        "geoapify:place-1",
        "osm:node/1",
    )
    assert canonical_rating_key(item) == "osm:node/1"


@pytest.mark.asyncio
async def test_rating_repository_aggregates_users_and_allows_updates(tmp_path) -> None:
    repository = RatingsRepository(str(tmp_path / "permplaces.db"))
    await repository.initialize()
    item = venue()

    first = await repository.set_rating(user_id=1, venue=item, score=5)
    assert first.average == 5
    assert first.count == 1

    second = await repository.set_rating(user_id=2, venue=item, score=3)
    assert second.average == 4
    assert second.count == 2

    updated = await repository.set_rating(user_id=1, venue=item, score=1)
    assert updated.average == 2
    assert updated.count == 2


@pytest.mark.asyncio
async def test_rating_repository_deduplicates_same_user_across_provider_aliases(
    tmp_path,
) -> None:
    repository = RatingsRepository(str(tmp_path / "permplaces.db"))
    await repository.initialize()

    geo_only = venue(source="geoapify", source_id="place-2")
    await repository.set_rating(user_id=7, venue=geo_only, score=2)

    merged = venue(
        source="osm",
        source_id="node/2",
        source_refs=(
            SourceRef("osm", "node/2"),
            SourceRef("geoapify", "place-2"),
        ),
    )
    await repository.set_rating(user_id=7, venue=merged, score=5)
    await repository.set_rating(user_id=8, venue=merged, score=3)

    summary = await repository.summary_for_venue(merged)

    assert summary.count == 2
    assert summary.average == 4


@pytest.mark.asyncio
async def test_rating_repository_enriches_venue_without_provider_provenance(
    tmp_path,
) -> None:
    repository = RatingsRepository(str(tmp_path / "permplaces.db"))
    await repository.initialize()
    item = venue()

    await repository.set_rating(user_id=1, venue=item, score=4)
    enriched = (await repository.enrich_many([item]))[0]

    assert enriched.community_rating == 4
    assert enriched.community_rating_count == 1
    assert enriched.field_sources == item.field_sources


@pytest.mark.asyncio
async def test_rating_repository_keeps_unknown_summary_empty(tmp_path) -> None:
    repository = RatingsRepository(str(tmp_path / "permplaces.db"))
    await repository.initialize()

    summary = await repository.summary_for_venue(venue(source_id="node/404"))

    assert summary.average is None
    assert summary.count == 0


@pytest.mark.asyncio
async def test_rating_repository_rejects_invalid_scores(tmp_path) -> None:
    repository = RatingsRepository(str(tmp_path / "permplaces.db"))
    await repository.initialize()
    item = venue()

    for invalid in (0, 6, True):
        with pytest.raises(ValueError, match="1 to 5"):
            await repository.set_rating(
                user_id=1,
                venue=item,
                score=invalid,  # type: ignore[arg-type]
            )


def test_canonical_rating_key_uses_primary_when_osm_alias_is_absent() -> None:
    item = replace(
        venue(source="geoapify", source_id="place-3"),
        source_refs=(SourceRef("geoapify", "place-3"),),
    )

    assert canonical_rating_key(item) == "geoapify:place-3"



@pytest.mark.asyncio
async def test_user_rating_uses_latest_alias_vote_and_remove_clears_all_aliases(
    tmp_path,
) -> None:
    repository = RatingsRepository(str(tmp_path / "permplaces.db"))
    await repository.initialize()

    geo_only = venue(source="geoapify", source_id="place-50")
    await repository.set_rating(user_id=10, venue=geo_only, score=2)

    merged = venue(
        source="osm",
        source_id="node/50",
        source_refs=(
            SourceRef("osm", "node/50"),
            SourceRef("geoapify", "place-50"),
        ),
    )
    await repository.set_rating(user_id=10, venue=merged, score=5)
    await repository.set_rating(user_id=11, venue=merged, score=4)

    assert await repository.user_rating_for_venue(user_id=10, venue=merged) == 5

    summary = await repository.remove_rating(user_id=10, venue=merged)

    assert await repository.user_rating_for_venue(user_id=10, venue=merged) is None
    assert summary.count == 1
    assert summary.average == 4


@pytest.mark.asyncio
async def test_batch_enrichment_keeps_aliases_and_venues_independent(tmp_path) -> None:
    repository = RatingsRepository(str(tmp_path / "permplaces.db"))
    await repository.initialize()

    first_geo = venue(source="geoapify", source_id="place-60")
    await repository.set_rating(user_id=1, venue=first_geo, score=2)

    first_merged = venue(
        source="osm",
        source_id="node/60",
        source_refs=(
            SourceRef("osm", "node/60"),
            SourceRef("geoapify", "place-60"),
        ),
    )
    await repository.set_rating(user_id=1, venue=first_merged, score=5)
    await repository.set_rating(user_id=2, venue=first_merged, score=3)

    second = venue(source="osm", source_id="node/61")
    await repository.set_rating(user_id=3, venue=second, score=1)

    enriched = await repository.enrich_many([first_merged, second])

    assert enriched[0].community_rating == 4
    assert enriched[0].community_rating_count == 2
    assert enriched[1].community_rating == 1
    assert enriched[1].community_rating_count == 1


@pytest.mark.asyncio
async def test_removing_missing_rating_is_idempotent(tmp_path) -> None:
    repository = RatingsRepository(str(tmp_path / "permplaces.db"))
    await repository.initialize()
    item = venue(source_id="node/70")

    summary = await repository.remove_rating(user_id=99, venue=item)

    assert summary.average is None
    assert summary.count == 0



def test_rating_identity_helpers_match_shared_venue_identity_contract() -> None:
    item = venue(
        source="geoapify",
        source_id="place-shared",
        source_refs=(
            SourceRef("geoapify", "place-shared"),
            SourceRef("osm", "node/shared"),
        ),
    )

    assert venue_rating_keys(item) == (
        "geoapify:place-shared",
        "osm:node/shared",
    )
    assert canonical_rating_key(item) == "osm:node/shared"
