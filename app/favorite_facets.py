from __future__ import annotations

import hashlib
from collections import Counter
from dataclasses import dataclass

from app.data import Venue
from app.favorite_search import normalize_favorite_search_text

MAX_FACET_OPTIONS = 30


@dataclass(frozen=True, slots=True)
class FavoriteFacetOption:
    token: str
    value: str
    label: str
    count: int


@dataclass(frozen=True, slots=True)
class FavoriteFacets:
    categories: tuple[FavoriteFacetOption, ...]
    districts: tuple[FavoriteFacetOption, ...]
    missing_district: int


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None


def _token(namespace: str, value: str) -> str:
    digest = hashlib.sha256(
        f"{namespace}\0{value}".encode()
    ).hexdigest()
    return digest[:20]


def _ranked_options(
    *,
    namespace: str,
    counts: Counter[str],
    labels: dict[str, str],
) -> tuple[FavoriteFacetOption, ...]:
    ranked = sorted(
        counts,
        key=lambda value: (
            -counts[value],
            normalize_favorite_search_text(labels[value]),
            labels[value],
            value,
        ),
    )[:MAX_FACET_OPTIONS]
    return tuple(
        FavoriteFacetOption(
            token=_token(namespace, value),
            value=value,
            label=labels[value],
            count=counts[value],
        )
        for value in ranked
    )


def build_favorite_facets(venues: list[Venue]) -> FavoriteFacets:
    category_counts: Counter[str] = Counter()
    category_labels: dict[str, str] = {}
    district_counts: Counter[str] = Counter()
    district_labels: dict[str, str] = {}
    missing_district = 0

    for venue in venues:
        category = _clean(venue.category)
        category_label = _clean(venue.category_label)
        if category is not None:
            category_counts[category] += 1
            category_labels.setdefault(
                category,
                category_label or category,
            )

        district = _clean(venue.district)
        if district is None:
            missing_district += 1
        else:
            district_counts[district] += 1
            district_labels.setdefault(district, district)

    return FavoriteFacets(
        categories=_ranked_options(
            namespace="category",
            counts=category_counts,
            labels=category_labels,
        ),
        districts=_ranked_options(
            namespace="district",
            counts=district_counts,
            labels=district_labels,
        ),
        missing_district=missing_district,
    )


def category_from_token(
    facets: FavoriteFacets,
    token: str,
) -> str | None:
    matches = [
        option.value
        for option in facets.categories
        if option.token == token
    ]
    return matches[0] if len(matches) == 1 else None


def district_from_token(
    facets: FavoriteFacets,
    token: str,
) -> str | None:
    matches = [
        option.value
        for option in facets.districts
        if option.token == token
    ]
    return matches[0] if len(matches) == 1 else None


def filter_favorites_by_facets(
    venues: list[Venue],
    *,
    category: str | None,
    district: str | None,
    district_missing: bool,
) -> list[Venue]:
    result: list[Venue] = []
    for venue in venues:
        if category is not None and venue.category != category:
            continue

        cleaned_district = _clean(venue.district)
        if district_missing:
            if cleaned_district is not None:
                continue
        elif district is not None and cleaned_district != district:
            continue

        result.append(venue)
    return result
