from __future__ import annotations

import re
from dataclasses import dataclass

from app.data import Venue
from app.tags import FAVORITE_TAG_LABELS

MAX_FAVORITE_SEARCH_LENGTH = 100

_SEPARATORS = re.compile(r"[^\w]+", re.UNICODE)
_WHITESPACE = re.compile(r"\s+")


@dataclass(frozen=True, slots=True)
class FavoriteSearchMatch:
    venue: Venue
    rank: int
    original_index: int


def normalize_favorite_search_text(value: str) -> str:
    normalized = value.casefold().replace("ё", "е")
    normalized = _SEPARATORS.sub(" ", normalized)
    return _WHITESPACE.sub(" ", normalized).strip()


def _search_fields(venue: Venue) -> tuple[str, ...]:
    tags = tuple(
        FAVORITE_TAG_LABELS[tag]
        for tag in venue.personal_tags
        if tag in FAVORITE_TAG_LABELS
    )
    return (
        venue.name,
        venue.address or "",
        venue.category_label,
        venue.district or "",
        venue.personal_note or "",
        " ".join(venue.cuisine),
        *tags,
    )


def _match_rank(
    *,
    query: str,
    tokens: tuple[str, ...],
    venue: Venue,
) -> int | None:
    normalized_fields = tuple(
        normalize_favorite_search_text(field)
        for field in _search_fields(venue)
        if field
    )
    haystack = " ".join(normalized_fields)
    if not all(token in haystack for token in tokens):
        return None

    name = normalize_favorite_search_text(venue.name)
    if name == query:
        return 0
    if name.startswith(query):
        return 1
    if all(token in name for token in tokens):
        return 2
    return 3


def search_favorites(
    venues: list[Venue],
    query: str,
) -> list[Venue]:
    normalized_query = normalize_favorite_search_text(query)
    if not normalized_query:
        return []

    tokens = tuple(normalized_query.split())
    matches: list[FavoriteSearchMatch] = []
    for index, venue in enumerate(venues):
        rank = _match_rank(
            query=normalized_query,
            tokens=tokens,
            venue=venue,
        )
        if rank is None:
            continue
        matches.append(
            FavoriteSearchMatch(
                venue=venue,
                rank=rank,
                original_index=index,
            )
        )

    matches.sort(key=lambda item: (item.rank, item.original_index))
    return [item.venue for item in matches]
