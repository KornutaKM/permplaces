# Favorite tags

PermPlaces supports a fixed set of private organizational tags for saved favorites.

## Tag set

The current keys and user-facing meanings are:

- `want` — `📌 Хочу сходить`;
- `return` — `🔁 Вернуться`;
- `work` — `💻 Для работы`;
- `family` — `👨‍👩‍👧 С семьёй`;
- `friends` — `👥 С друзьями`.

These tags express the user's own organization or intent. They are not provider facts and must not
be used as evidence that a venue objectively supports work, children, groups, atmosphere or any
other characteristic.

## Storage and identity

Tags are stored in the local SQLite `favorite_tags` table and use the same exact
`provider:source_id` identity contract as favorites, ratings and personal notes.

A tag can be created only when one of the venue's exact identities exists in the current user's
favorite alias index. No fuzzy name, address, phone or website matching is used.

Reads consider all known provider aliases, so a tag attached to a historical Geoapify-only favorite
remains visible if the venue later appears as an OSM + Geoapify merged result.

## Telegram behavior

From a favorite detail card the user can open `🏷 Мои метки` and toggle any predefined tag.
The favorites result list also exposes `🏷 Фильтр по метке`.

Filtering is local and deterministic. It never triggers an external provider request.

If the user removes the last tag matching the active filter, PermPlaces clears that filter instead
of leaving the in-memory favorites result set empty.

## Lifecycle

Removing a favorite deletes personal notes and tags attached to every known exact alias for that
favorite in the same SQLite transaction.

User-data deletion through `/mydata` also removes all tag rows for that Telegram user.

## Privacy and export

`/mydata` reports the number of stored tag rows. User-data export format v3 contains a
`favorite_tags` collection with:

- exact identity key;
- stable tag key;
- update timestamp in UTC.

The internal UI label is not required for reconstruction because the stable tag key is the
versioned application value.

See `docs/PRIVACY.md`, `docs/DATA_EXPORT.md` and `docs/FAVORITES.md`.
