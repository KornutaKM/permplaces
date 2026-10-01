import sqlite3
from dataclasses import replace

import pytest

from app.data import SourceRef, Venue
from app.storage import FavoritesRepository
from app.tags import (
    FAVORITE_TAG_KEYS,
    FavoriteTagsRepository,
    favorite_tag_counts,
)


def venue(
    *,
    source: str = "osm",
    source_id: str = "node/tag",
    source_refs: tuple[SourceRef, ...] = (),
) -> Venue:
    return Venue(
        id=f"{source}:{source_id}",
        name="Tagged place",
        category="cafe",
        category_label="Кофейня",
        latitude=58.01,
        longitude=56.25,
        source=source,
        source_id=source_id,
        source_refs=source_refs,
    )


async def save_favorite(path: str, *, user_id: int, item: Venue) -> None:
    repository = FavoritesRepository(path)
    await repository.initialize()
    assert await repository.toggle(user_id=user_id, venue=item) is True


@pytest.mark.asyncio
async def test_tag_requires_saved_favorite_and_known_key(tmp_path) -> None:
    path = str(tmp_path / "permplaces.db")
    tags = FavoriteTagsRepository(path)
    await tags.initialize()
    item = venue()

    with pytest.raises(ValueError, match="saved favorite"):
        await tags.toggle_tag(user_id=1, venue=item, tag="want")

    await save_favorite(path, user_id=1, item=item)
    with pytest.raises(ValueError, match="unsupported"):
        await tags.toggle_tag(user_id=1, venue=item, tag="custom")


@pytest.mark.asyncio
async def test_toggle_tag_adds_and_removes_deterministically(tmp_path) -> None:
    path = str(tmp_path / "permplaces.db")
    tags = FavoriteTagsRepository(path)
    await tags.initialize()
    item = venue()
    await save_favorite(path, user_id=2, item=item)

    assert await tags.toggle_tag(user_id=2, venue=item, tag="want") is True
    assert await tags.toggle_tag(user_id=2, venue=item, tag="work") is True
    assert await tags.tags_for_venue(user_id=2, venue=item) == ("want", "work")

    assert await tags.toggle_tag(user_id=2, venue=item, tag="want") is False
    assert await tags.tags_for_venue(user_id=2, venue=item) == ("work",)


@pytest.mark.asyncio
async def test_tags_follow_provider_aliases(tmp_path) -> None:
    path = str(tmp_path / "permplaces.db")
    tags = FavoriteTagsRepository(path)
    await tags.initialize()

    geo = venue(source="geoapify", source_id="place-tag")
    await save_favorite(path, user_id=3, item=geo)
    assert await tags.toggle_tag(user_id=3, venue=geo, tag="return") is True

    merged = venue(
        source="osm",
        source_id="node/tag",
        source_refs=(
            SourceRef("osm", "node/tag"),
            SourceRef("geoapify", "place-tag"),
        ),
    )

    assert await tags.tags_for_venue(user_id=3, venue=merged) == ("return",)
    assert await tags.toggle_tag(user_id=3, venue=merged, tag="return") is False
    assert await tags.tags_for_venue(user_id=3, venue=merged) == ()


@pytest.mark.asyncio
async def test_new_tag_prefers_saved_osm_identity_when_available(tmp_path) -> None:
    path = str(tmp_path / "permplaces.db")
    tags = FavoriteTagsRepository(path)
    await tags.initialize()
    merged = venue(
        source="geoapify",
        source_id="place-canonical",
        source_refs=(
            SourceRef("geoapify", "place-canonical"),
            SourceRef("osm", "node/canonical"),
        ),
    )
    await save_favorite(path, user_id=4, item=merged)

    assert await tags.toggle_tag(user_id=4, venue=merged, tag="family") is True

    with sqlite3.connect(path) as database:
        rows = database.execute(
            """
            SELECT identity_key, tag
            FROM favorite_tags
            WHERE user_id = 4
            """
        ).fetchall()

    assert rows == [("osm:node/canonical", "family")]


@pytest.mark.asyncio
async def test_enrich_many_is_user_scoped_alias_aware_and_ordered(tmp_path) -> None:
    path = str(tmp_path / "permplaces.db")
    tags = FavoriteTagsRepository(path)
    await tags.initialize()
    first = venue(source="geoapify", source_id="place-first")
    second = venue(source="osm", source_id="node/second")
    await save_favorite(path, user_id=5, item=first)
    await save_favorite(path, user_id=6, item=second)

    await tags.toggle_tag(user_id=5, venue=first, tag="friends")
    await tags.toggle_tag(user_id=5, venue=first, tag="want")
    await tags.toggle_tag(user_id=6, venue=second, tag="work")

    merged_first = venue(
        source="osm",
        source_id="node/first",
        source_refs=(
            SourceRef("osm", "node/first"),
            SourceRef("geoapify", "place-first"),
        ),
    )
    enriched = await tags.enrich_many(
        user_id=5,
        venues=[merged_first, second],
    )

    assert enriched[0].personal_tags == ("want", "friends")
    assert enriched[1].personal_tags == ()


def test_favorite_tag_counts_ignores_duplicates_and_unknown_values() -> None:
    first = replace(
        venue(),
        personal_tags=("want", "want", "unknown"),
    )
    second = replace(
        venue(source_id="node/tag-2"),
        personal_tags=("want", "work"),
    )

    counts = favorite_tag_counts([first, second])

    assert set(counts) == set(FAVORITE_TAG_KEYS)
    assert counts["want"] == 2
    assert counts["work"] == 1
    assert counts["return"] == 0
    assert counts["family"] == 0
    assert counts["friends"] == 0
