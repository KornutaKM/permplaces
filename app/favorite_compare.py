from __future__ import annotations

import hashlib
from dataclasses import dataclass

from app.data import Venue

MAX_COMPARE_OPTIONS = 20


@dataclass(frozen=True, slots=True)
class FavoriteCompareOption:
    token: str
    venue: Venue


def _compare_token(venue_id: str) -> str:
    return hashlib.sha256(
        f"favorite-compare\0{venue_id}".encode()
    ).hexdigest()[:20]


def favorite_compare_options(
    venues: list[Venue],
    *,
    primary_id: str,
    limit: int = MAX_COMPARE_OPTIONS,
) -> tuple[FavoriteCompareOption, ...]:
    bounded_limit = max(1, min(limit, MAX_COMPARE_OPTIONS))
    options: list[FavoriteCompareOption] = []
    for venue in venues:
        if venue.id == primary_id:
            continue
        options.append(
            FavoriteCompareOption(
                token=_compare_token(venue.id),
                venue=venue,
            )
        )
        if len(options) >= bounded_limit:
            break
    return tuple(options)


def favorite_from_compare_token(
    options: tuple[FavoriteCompareOption, ...],
    token: str,
) -> Venue | None:
    matches = [
        option.venue
        for option in options
        if option.token == token
    ]
    return matches[0] if len(matches) == 1 else None
