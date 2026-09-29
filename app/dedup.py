from __future__ import annotations

import re
from dataclasses import replace
from math import asin, cos, radians, sin, sqrt
from urllib.parse import urlsplit

from app.data import FieldSource, SourceRef, Venue

_NON_ALNUM = re.compile(r"[^\w]+", re.UNICODE)
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
        if value is None or value == "" or value == ():
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


def same_venue(a: Venue, b: Venue) -> bool:
    if a.source == b.source and a.source_id == b.source_id:
        return True

    distance = _distance_m(a, b)
    if distance > 500:
        return False

    phone_a = _normalize_phone(a.phone)
    phone_b = _normalize_phone(b.phone)
    if phone_a and phone_a == phone_b:
        return True

    host_a = _normalize_host(a.website)
    host_b = _normalize_host(b.website)
    if host_a and host_a == host_b:
        return True

    name_a = _normalize_text(a.name)
    name_b = _normalize_text(b.name)
    if not name_a or name_a != name_b:
        return False

    address_a = _normalize_text(a.address)
    address_b = _normalize_text(b.address)
    if address_a and address_a == address_b:
        return True

    return distance <= 40


def _field_source(venue: Venue, field_name: str) -> FieldSource:
    for item in venue.field_sources:
        if item.field_name == field_name:
            return item
    return FieldSource(
        field_name=field_name,
        provider=venue.source,
        source_id=venue.source_id,
    )


def _missing(value: object) -> bool:
    return value is None or value == "" or value == ()


def merge_venues(primary: Venue, secondary: Venue) -> Venue:
    primary = ensure_provenance(primary)
    secondary = ensure_provenance(secondary)

    updates: dict[str, object] = {}
    chosen_sources: dict[str, FieldSource] = {
        item.field_name: item for item in primary.field_sources
    }

    for field_name in (
        "address",
        "district",
        "opening_hours",
        "phone",
        "website",
        "cuisine",
        "outdoor_seating",
        "wifi",
        "kids_area",
        "highchair",
        "changing_table",
        "price_label",
    ):
        if _missing(getattr(primary, field_name)) and not _missing(
            getattr(secondary, field_name)
        ):
            updates[field_name] = getattr(secondary, field_name)
            chosen_sources[field_name] = _field_source(secondary, field_name)

    # Rating, its scale, and review count are an atomic provider-backed group.
    # Never make a synthetic score by combining metadata from different providers.
    if primary.rating is None and secondary.rating is not None:
        updates["rating"] = secondary.rating
        updates["rating_scale"] = secondary.rating_scale
        updates["review_count"] = secondary.review_count
        chosen_sources["rating"] = _field_source(secondary, "rating")
        chosen_sources.pop("rating_scale", None)
        chosen_sources.pop("review_count", None)
        if secondary.rating_scale is not None:
            chosen_sources["rating_scale"] = _field_source(
                secondary,
                "rating_scale",
            )
        if secondary.review_count is not None:
            chosen_sources["review_count"] = _field_source(
                secondary,
                "review_count",
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
        chosen_sources[key] for key in sorted(chosen_sources)
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
