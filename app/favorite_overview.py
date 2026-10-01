from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from html import escape

from app.data import Venue
from app.favorite_search import normalize_favorite_search_text
from app.tags import FAVORITE_TAG_KEYS, FAVORITE_TAG_LABELS

DEFAULT_OVERVIEW_LIMIT = 5


@dataclass(frozen=True, slots=True)
class FavoriteOverview:
    total: int
    with_notes: int
    with_tags: int
    tag_counts: tuple[tuple[str, int], ...]
    categories: tuple[tuple[str, int], ...]
    districts: tuple[tuple[str, int], ...]
    missing_district: int


def _clean_label(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None


def _rank_counts(
    counts: Counter[str],
    *,
    limit: int,
) -> tuple[tuple[str, int], ...]:
    return tuple(
        sorted(
            counts.items(),
            key=lambda item: (
                -item[1],
                normalize_favorite_search_text(item[0]),
                item[0],
            ),
        )[:limit]
    )


def build_favorite_overview(
    venues: list[Venue],
    *,
    limit: int = DEFAULT_OVERVIEW_LIMIT,
) -> FavoriteOverview:
    bounded_limit = max(1, limit)
    category_counts: Counter[str] = Counter()
    district_counts: Counter[str] = Counter()
    tag_counter: Counter[str] = Counter()

    with_notes = 0
    with_tags = 0
    missing_district = 0

    for venue in venues:
        if venue.personal_note and venue.personal_note.strip():
            with_notes += 1

        known_tags = {
            tag
            for tag in venue.personal_tags
            if tag in FAVORITE_TAG_LABELS
        }
        if known_tags:
            with_tags += 1
            tag_counter.update(known_tags)

        category = _clean_label(venue.category_label)
        if category is not None:
            category_counts[category] += 1

        district = _clean_label(venue.district)
        if district is None:
            missing_district += 1
        else:
            district_counts[district] += 1

    tag_counts = tuple(
        (tag, tag_counter[tag])
        for tag in FAVORITE_TAG_KEYS
        if tag_counter[tag] > 0
    )
    return FavoriteOverview(
        total=len(venues),
        with_notes=with_notes,
        with_tags=with_tags,
        tag_counts=tag_counts,
        categories=_rank_counts(category_counts, limit=bounded_limit),
        districts=_rank_counts(district_counts, limit=bounded_limit),
        missing_district=missing_district,
    )


def render_favorite_overview(overview: FavoriteOverview) -> str:
    lines = [
        "📊 <b>Обзор избранного</b>",
        "",
        f"❤️ Сохранено мест: <b>{overview.total}</b>",
        f"📝 С личной заметкой: <b>{overview.with_notes}</b>",
        f"🏷 С личными метками: <b>{overview.with_tags}</b>",
    ]

    if overview.tag_counts:
        lines.extend(["", "<b>Ваши метки</b>"])
        for tag, count in overview.tag_counts:
            label = FAVORITE_TAG_LABELS.get(tag)
            if label is not None:
                lines.append(f"• {escape(label)}: <b>{count}</b>")

    if overview.categories:
        lines.extend(["", "<b>Категории сохранённых карточек</b>"])
        for label, count in overview.categories:
            lines.append(f"• {escape(label)}: <b>{count}</b>")

    if overview.districts or overview.missing_district:
        lines.extend(["", "<b>Районы, указанные источниками</b>"])
        for district, count in overview.districts:
            lines.append(f"• {escape(district)}: <b>{count}</b>")
        if overview.missing_district:
            lines.append(
                "• Район не указан в сохранённой карточке: "
                f"<b>{overview.missing_district}</b>"
            )

    lines.extend(
        [
            "",
            "Обзор строится только по уже сохранённым карточкам и вашим локальным данным. "
            "Он не запрашивает внешние каталоги.",
        ]
    )
    return "\n".join(lines)
