# User data export

PermPlaces can export the current user's persistent application data as UTF-8 JSON from
`/mydata` → `📦 Скачать JSON`.

## Format contract

Current export format version: `3`.

Top-level structure:

```json
{
  "format": "permplaces-user-data",
  "format_version": 3,
  "favorites": [],
  "community_ratings": [],
  "favorite_notes": [],
  "favorite_tags": []
}
```

The export intentionally does **not** include the Telegram user ID. The request is scoped by the
authenticated Telegram update that triggered the export.

### Favorites

Each favorite entry contains:

- the stored `venue_id`;
- the SQLite `created_at` value as `saved_at_utc`;
- the stored venue snapshot as structured JSON when it is valid;
- `payload_status`, which is `ok` or `invalid`.

A venue snapshot can contain provider-backed place fields such as venue coordinates, address,
source references and provenance because those fields are part of the user's saved favorite.

If a historical favorite payload is malformed, PermPlaces does not echo its raw bytes into the
export. The row is represented with `venue: null` and `payload_status: invalid`.

### Community ratings

Each rating entry contains:

- exact `provider:source_id` venue key;
- the user's numeric 1–5 score;
- the rating update timestamp converted from the internal nanosecond timestamp to UTC ISO 8601.

### Favorite notes

Each personal-note entry contains:

- exact `provider:source_id` identity key;
- the user's note text;
- the note update timestamp converted to UTC ISO 8601.

Notes are user-authored local data, not provider facts. They are exported because they are
persistent user data.

### Favorite tags

Each tag entry contains:

- exact `provider:source_id` identity key;
- stable predefined tag key;
- the tag update timestamp converted to UTC ISO 8601.

Tags are user-selected local organization data, not provider facts. They are exported as
persistent user data.

The internal `favorite_identity_aliases` index is derived operational data and is not exported
separately. Known provider aliases already remain available inside valid favorite
`source_refs`.

## Excluded data

The JSON export does not contain:

- Telegram user ID;
- bot token or provider API keys;
- provider request-budget counters;
- application cache contents;
- live search/FSM state;
- a location-history or search-history dataset, because PermPlaces does not persist those tables.

## Delivery

The file is generated in memory on demand and sent back as a Telegram document named
`permplaces-mydata.json`. PermPlaces does not create a second persistent export file on the
application host.

Once delivered through Telegram, the message/document is also subject to Telegram's own storage
and retention behavior, which is outside the PermPlaces SQLite contract.
