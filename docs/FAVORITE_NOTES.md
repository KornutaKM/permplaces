# Favorite personal notes

PermPlaces supports a private free-text note for a saved favorite.

## Scope

A note belongs to one Telegram user and one saved favorite identity. It is local PermPlaces data:

- maximum length: 500 characters;
- stored in SQLite;
- never sent to OpenStreetMap, Geoapify, 2GIS, Foursquare or another places provider;
- never treated as provider provenance or a factual venue attribute;
- rendered explicitly as `📝 Ваша заметка`.

Notes are available only from the current user's favorites flow. PermPlaces refuses to create a
note when none of the venue's exact provider identities exists in that user's favorite index.

## Alias behavior

Notes use the same exact `provider:source_id` identity contract as favorites and community
ratings.

Reads consider every known provider alias. This allows a note created on an older Geoapify-only
favorite to remain visible after the same venue later appears with OSM + Geoapify identities.

When a note is edited, PermPlaces stores it under the preferred exact identity that is also
present in the user's current favorite alias index. If OSM is known and is part of the saved
favorite, OSM is preferred.

No fuzzy name/address/phone matching is used.

## Lifecycle

The user can:

1. open a venue from `❤️ Избранное`;
2. choose `📝 Заметка`;
3. enter or replace the note text;
4. remove the note explicitly.

Removing the favorite also removes personal notes attached to all known aliases for that favorite
inside the same SQLite transaction.

## Security and rendering

User text is HTML-escaped before it is rendered in Telegram cards. A note cannot inject Telegram
HTML markup.

The note text is never written into the provider-backed favorite snapshot. It lives in the
separate `favorite_notes` table and is enriched only when the current user's favorites are read.

## Privacy and export

`/mydata` counts personal notes as persistent user data. Confirmed data deletion removes them in
the same transaction as favorites and community ratings.

User-data export format v2 contains a `favorite_notes` collection with:

- exact identity key;
- note text;
- update timestamp in UTC.

See `docs/PRIVACY.md` and `docs/DATA_EXPORT.md`.
