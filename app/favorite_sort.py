from __future__ import annotations

from dataclasses import dataclass

from app.data import Venue
from app.favorite_search import normalize_favorite_search_text
from app.tags import FAVORITE_TAG_LABELS

FAVORITE_SORT_LABELS: dict[str, str] = {
    "recent": "🕒 Недавно сохранённые",
    "name": "🔤 По названию",
    "notes": "📝 Сначала с заметкой",
    "tags": "🏷 Сначала с метками",
}
DEFAULT_FAVORITE_SORT = "recent"


@dataclass(frozen=True, slots=True)
class FavoriteSortItem:
    venue: Venue
    original_index: int


def _has_note(venue: Venue) -> bool:
    return bool(venue.personal_note and venue.personal_note.strip())


def _known_tag_count(venue: Venue) -> int:
    return len(
        {
            tag
            for tag in venue.personal_tags
            if tag in FAVORITE_TAG_LABELS
        }
    )


def sort_favorites(
    venues: list[Venue],
    sort_key: str,
) -> list[Venue]:
    if sort_key not in FAVORITE_SORT_LABELS:
        sort_key = DEFAULT_FAVORITE_SORT

    items = [
        FavoriteSortItem(venue=venue, original_index=index)
        for index, venue in enumerate(venues)
    ]

    if sort_key == "recent":
        return [item.venue for item in items]

    if sort_key == "name":
        items.sort(
            key=lambda item: (
                normalize_favorite_search_text(item.venue.name),
                item.original_index,
            )
        )
    elif sort_key == "notes":
        items.sort(
            key=lambda item: (
                0 if _has_note(item.venue) else 1,
                item.original_index,
            )
        )
    elif sort_key == "tags":
        items.sort(
            key=lambda item: (
                -_known_tag_count(item.venue),
                item.original_index,
            )
        )

    return [item.venue for item in items]
