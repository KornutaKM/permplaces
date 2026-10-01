from __future__ import annotations

from app.data import SourceRef, Venue


def source_identity_key(provider: str, source_id: str) -> str:
    return f"{provider}:{source_id}"


def venue_identity_refs(venue: Venue) -> tuple[SourceRef, ...]:
    if venue.source_refs:
        return venue.source_refs
    return (
        SourceRef(
            provider=venue.source,
            source_id=venue.source_id,
            source_url=venue.source_url,
        ),
    )


def venue_identity_keys(venue: Venue) -> tuple[str, ...]:
    keys: list[str] = [source_identity_key(venue.source, venue.source_id)]
    keys.extend(
        source_identity_key(ref.provider, ref.source_id)
        for ref in venue_identity_refs(venue)
    )

    unique: list[str] = []
    seen: set[str] = set()
    for key in keys:
        if key not in seen:
            unique.append(key)
            seen.add(key)
    return tuple(unique)


def canonical_venue_key(venue: Venue) -> str:
    if venue.source == "osm":
        return source_identity_key(venue.source, venue.source_id)

    for ref in venue_identity_refs(venue):
        if ref.provider == "osm":
            return source_identity_key(ref.provider, ref.source_id)

    return source_identity_key(venue.source, venue.source_id)
