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
    cuisines: tuple[FavoriteFacetOption, ...]
    missing_cuisine: int


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
    cuisine_counts: Counter[str] = Counter()
    cuisine_labels: dict[str, str] = {}
    missing_cuisine = 0

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

        normalized_cuisines: set[str] = set()
        for raw_cuisine in venue.cuisine:
            cleaned_cuisine = _clean(raw_cuisine)
            if cleaned_cuisine is None:
                continue
            normalized_cuisine = cleaned_cuisine.casefold()
            normalized_cuisines.add(normalized_cuisine)
            cuisine_labels.setdefault(
                normalized_cuisine,
                cleaned_cuisine,
            )
        if not normalized_cuisines:
            missing_cuisine += 1
        else:
            cuisine_counts.update(normalized_cuisines)

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
        cuisines=_ranked_options(
            namespace="cuisine",
            counts=cuisine_counts,
            labels=cuisine_labels,
        ),
        missing_cuisine=missing_cuisine,
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


def cuisine_from_token(
    facets: FavoriteFacets,
    token: str,
) -> str | None:
    matches = [
        option.value
        for option in facets.cuisines
        if option.token == token
    ]
    return matches[0] if len(matches) == 1 else None


def filter_favorites_by_facets(
    venues: list[Venue],
    *,
    category: str | None,
    district: str | None,
    district_missing: bool,
    cuisine: str | None,
    cuisine_missing: bool,
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

        venue_cuisines = {
            cleaned.casefold()
            for value in venue.cuisine
            if (cleaned := _clean(value)) is not None
        }
        if cuisine_missing:
            if venue_cuisines:
                continue
        elif cuisine is not None and cuisine not in venue_cuisines:
            continue

        result.append(venue)
    return result
