# Privacy and user data controls

PermPlaces stores only a small amount of application data tied to a Telegram user ID.

## Persistent data

The SQLite database stores, per Telegram user:

- favorite venue payloads, with provider aliases used only to recognize the same saved place;
- numeric 1–5 PermPlaces community ratings using the same provider-alias identity contract.

Provider request-budget counters are application/operator state and are not user-specific.

The bot does not persist a separate location-history table or search-history table. Current
search state, including a location sent for nearby search, lives in the in-memory aiogram FSM for
the running process.

This document describes PermPlaces application storage only. It does not control Telegram's own
chat/message retention.

## Inspecting your stored data

The Telegram command:

```text
/mydata
```

returns only aggregate counts for the current Telegram user:

- number of favorites;
- number of community-rating rows.

It does not print the Telegram user ID, favorite payloads, coordinates, provider keys or other
users' counts.

## Deleting your stored data

If persistent data exists, `/mydata` shows an explicit delete action. Deletion requires a second
confirmation.

On confirmation PermPlaces:

1. deletes all favorites for the current Telegram user;
2. deletes all community-rating rows for the current Telegram user, including historical provider
   aliases;
3. commits both deletions in one SQLite transaction;
4. clears the current in-memory search/FSM state.

Provider budget counters are not deleted because they are shared operational state, not personal
user data.

The deletion is idempotent: repeating it after the rows are gone deletes zero additional rows.

## Community aggregates after deletion

Deleting one user's ratings changes future PermPlaces community aggregates because that user's
votes no longer contribute. External provider ratings and source provenance are unaffected.

## Operational backups

SQLite backups can still contain user data that existed at the time the backup was created.
PermPlaces does not automatically rewrite historical backup files after an in-app deletion.
Operators must apply their backup retention policy separately.
