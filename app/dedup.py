from __future__ import annotations

import re
from dataclasses import replace
from math import asin, cos, radians, sin, sqrt
from urllib.parse import urlsplit

from app.data import FieldSource, SourceRef, Venue

_NON_ALNUM = re.compile(r"[^\w]+", re.UNICODE)
_GENERIC_NAME_TOKENS = frozenset(
    {
        "кафе",
        "кофейня",
        "ресторан",
        "бар",
        "паб",
        "cafe",
        "coffee",
        "restaurant",
        "bar",
        "pub",
    }
)
_ADDRESS_STOPWORDS = frozenset(
    {
        "г",
        "город",
        "пермь",
        "perm",
        "ул",
        "улица",
        "пр",
        "проспект",
        "пр-т",
        "дом",
        "д",
    }
)
_MERGE_FIELDS = (
    "name",
    "category",
    "category_label",
    "latitude",
    "longitude",
    "address",
    "district",
    "opening_hours",
    "phone",
    "website",
    "menu_url",
    "photos",
    "cuisine",
    "outdoor_seating",
    "wifi",
    "kids_area",
    "highchair",
    "changing_table",
    "price_label",
    "rating",
    "rating_scale",
    "review_count",
)


def _normalize_text(value: str | None) -> str:
    if not value:
        return ""
    normalized = value.casefold().replace("ё", "е")
    return " ".join(_NON_ALNUM.sub(" ", normalized).split())


def _canonical_name(value: str | None) -> str:
    tokens = _normalize_text(value).split()
    while len(tokens) > 1 and tokens[0] in _GENERIC_NAME_TOKENS:
        tokens.pop(0)
    while len(tokens) > 1 and tokens[-1] in _GENERIC_NAME_TOKENS:
        tokens.pop()
    return " ".join(tokens)


def _address_signature(value: str | None) -> tuple[str, ...]:
    tokens = _normalize_text(value).split()
    return tuple(token for token in tokens if token not in _ADDRESS_STOPWORDS)


def _normalize_phone(value: str | None) -> str:
    if not value:
        return ""
    digits = "".join(char for char in value if char.isdigit())
    return digits[-10:] if len(digits) >= 10 else digits


def _normalize_host(value: str | None) -> str:
    if not value:
        return ""
    parsed = urlsplit(value.strip())
    host = (parsed.hostname or "").casefold()
    return host.removeprefix("www.")


def _distance_m(a: Venue, b: Venue) -> int:
    earth_radius_m = 6_371_000
    lat1 = radians(a.latitude)
    lat2 = radians(b.latitude)
    dlat = radians(b.latitude - a.latitude)
    dlon = radians(b.longitude - a.longitude)
    haversine = (
        sin(dlat / 2) ** 2
        + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
    )
    return round(2 * earth_radius_m * asin(sqrt(haversine)))


def source_ref(venue: Venue) -> SourceRef:
    return SourceRef(
        provider=venue.source,
        source_id=venue.source_id,
        source_url=venue.source_url,
    )


def ensure_provenance(venue: Venue) -> Venue:
    refs = venue.source_refs or (source_ref(venue),)
    if venue.field_sources:
        return replace(venue, source_refs=refs)

    provenance: list[FieldSource] = []
    for field_name in _MERGE_FIELDS:
        value = getattr(venue, field_name)
        if _missing(value):
            continue
        provenance.append(
            FieldSource(
                field_name=field_name,
                provider=venue.source,
                source_id=venue.source_id,
            )
        )
    return replace(
        venue,
        source_refs=refs,
        field_sources=tuple(provenance),
    )


def _same_address(a: Venue, b: Venue) -> bool:
    first = _address_signature(a.address)
    second = _address_signature(b.address)
    return bool(first and second and first == second)


def same_venue(a: Venue, b: Venue) -> bool:
    if a.source == b.source and a.source_id == b.source_id:
        return True

    distance = _distance_m(a, b)
    if distance > 500:
        return False

    same_address = _same_address(a, b)

    phone_a = _normalize_phone(a.phone)
    phone_b = _normalize_phone(b.phone)
    # Shared call-center numbers exist. A matching phone is strong only
    # inside a branch-sized radius, or when the address also agrees.
    if phone_a and phone_a == phone_b and (same_address or distance <= 120):
        return True

    host_a = _normalize_host(a.website)
    host_b = _normalize_host(b.website)
    # Chain branches commonly share one website. Do not merge them on host
    # identity alone unless coordinates/address independently support it.
    if host_a and host_a == host_b and (same_address or distance <= 40):
        return True

    name_a = _normalize_text(a.name)
    name_b = _normalize_text(b.name)
    if name_a and name_a == name_b:
        if same_address:
            return True
        return distance <= 40

    canonical_a = _canonical_name(a.name)
    canonical_b = _canonical_name(b.name)
    if not canonical_a or canonical_a != canonical_b:
        return False

    # "Кафе Север" and "Север" can be the same place, but stripping generic
    # venue-type words is only safe with a very close point or matching address.
    if same_address:
        return distance <= 250
    return distance <= 25


def _field_sources_for(venue: Venue, field_name: str) -> tuple[FieldSource, ...]:
    sources = tuple(
        item for item in venue.field_sources if item.field_name == field_name
    )
    if sources:
        return sources
    return (
        FieldSource(
            field_name=field_name,
            provider=venue.source,
            source_id=venue.source_id,
        ),
    )


def _missing(value: object) -> bool:
    return value is None or value == "" or value == ()


def _equivalent_field_value(field_name: str, first: object, second: object) -> bool:
    if _missing(first) or _missing(second):
        return False
    if field_name in {"name", "address", "district", "opening_hours"}:
        if not isinstance(first, str) or not isinstance(second, str):
            return False
        return _normalize_text(first) == _normalize_text(second)
    if field_name == "phone":
        if not isinstance(first, str) or not isinstance(second, str):
            return False
        normalized = _normalize_phone(first)
        return bool(normalized and normalized == _normalize_phone(second))
    return first == second


def _append_field_sources(
    chosen: list[FieldSource],
    additions: tuple[FieldSource, ...],
) -> None:
    existing = {
        (item.field_name, item.provider, item.source_id)
        for item in chosen
    }
    for item in additions:
        key = (item.field_name, item.provider, item.source_id)
        if key not in existing:
            chosen.append(item)
            existing.add(key)


def merge_venues(primary: Venue, secondary: Venue) -> Venue:
    primary = ensure_provenance(primary)
    secondary = ensure_provenance(secondary)

    updates: dict[str, object] = {}
    chosen_sources = list(primary.field_sources)

    enrichable_fields = (
        "address",
        "district",
        "opening_hours",
        "phone",
        "website",
        "menu_url",
        "photos",
        "cuisine",
        "outdoor_seating",
        "wifi",
        "kids_area",
        "highchair",
        "changing_table",
        "price_label",
    )
    for field_name in enrichable_fields:
        primary_value = getattr(primary, field_name)
        secondary_value = getattr(secondary, field_name)
        if _missing(primary_value) and not _missing(secondary_value):
            updates[field_name] = secondary_value
            _append_field_sources(
                chosen_sources,
                _field_sources_for(secondary, field_name),
            )
        elif _equivalent_field_value(
            field_name,
            primary_value,
            secondary_value,
        ):
            _append_field_sources(
                chosen_sources,
                _field_sources_for(secondary, field_name),
            )

    # Corroborating providers may confirm the retained identity fields without
    # changing provider priority or rewriting the displayed value.
    for field_name in ("name", "category", "category_label"):
        if _equivalent_field_value(
            field_name,
            getattr(primary, field_name),
            getattr(secondary, field_name),
        ):
            _append_field_sources(
                chosen_sources,
                _field_sources_for(secondary, field_name),
            )

    # Rating, its scale, and review count are an atomic provider-backed group.
    # Never make a synthetic score by combining metadata from different providers.
    if primary.rating is None and secondary.rating is not None:
        updates["rating"] = secondary.rating
        updates["rating_scale"] = secondary.rating_scale
        updates["review_count"] = secondary.review_count
        for field_name in ("rating", "rating_scale", "review_count"):
            value = getattr(secondary, field_name)
            if not _missing(value):
                _append_field_sources(
                    chosen_sources,
                    _field_sources_for(secondary, field_name),
                )
    elif (
        primary.rating is not None
        and secondary.rating is not None
        and primary.rating == secondary.rating
        and primary.rating_scale == secondary.rating_scale
        and primary.review_count == secondary.review_count
    ):
        for field_name in ("rating", "rating_scale", "review_count"):
            value = getattr(secondary, field_name)
            if not _missing(value):
                _append_field_sources(
                    chosen_sources,
                    _field_sources_for(secondary, field_name),
                )

    refs: list[SourceRef] = list(primary.source_refs)
    existing_refs = {(item.provider, item.source_id) for item in refs}
    for item in secondary.source_refs:
        key = (item.provider, item.source_id)
        if key not in existing_refs:
            refs.append(item)
            existing_refs.add(key)

    updates["source_refs"] = tuple(refs)
    updates["field_sources"] = tuple(
        sorted(
            chosen_sources,
            key=lambda item: (item.field_name, item.provider, item.source_id),
        )
    )
    return replace(primary, **updates)


def merge_provider_results(
    provider_results: list[list[Venue]],
    *,
    limit: int,
) -> list[Venue]:
    merged: list[Venue] = []

    for result_set in provider_results:
        for raw_venue in result_set:
            venue = ensure_provenance(raw_venue)
            for index, current in enumerate(merged):
                if same_venue(current, venue):
                    merged[index] = merge_venues(current, venue)
                    break
            else:
                merged.append(venue)

    return merged[:limit]
