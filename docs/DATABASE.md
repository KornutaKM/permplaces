# SQLite schema and migrations

PermPlaces uses one SQLite database for favorites, community ratings and persistent provider
budget counters.

## Schema version

The application schema is versioned with SQLite `PRAGMA user_version`.

Current version: `1`.

Startup calls one central `initialize_database()` function before Telegram polling begins. The
initializer:

- enables WAL mode;
- takes an immediate migration transaction;
- creates missing application tables and indexes;
- validates required columns on existing tables;
- refuses to run if the database schema version is newer than the application;
- updates `PRAGMA user_version` only after validation succeeds.

Databases created by earlier PermPlaces versions have `user_version=0`. They are upgraded in
place without deleting existing favorites or community ratings.

Malformed legacy tables are not silently accepted: startup fails before readiness instead of
pretending that the database is compatible.

## Current tables

Application-owned tables:

- `favorites` — saved venue payloads per Telegram user;
- `venue_ratings` — local 1–5 community ratings;
- `provider_daily_request_budget` — persistent application-side provider request counters.

The rating index `idx_venue_ratings_venue_key` is part of the schema contract.

## Operator inspection

The admin CLI can verify SQLite integrity and print only schema/data counters:

```bash
python -m app.db_admin inspect --database data/permplaces.db
```

Example:

```text
inspect_ok path=data/permplaces.db schema_version=1 favorites=12 ratings=34 provider_budget_rows=1
```

The command does not print favorite payloads, Telegram user IDs, provider keys, coordinates or
rating rows.

Use `inspect` after a backup/restore drill and before diagnosing schema-related startup failures.
It runs `PRAGMA quick_check` first.

## Backward and forward compatibility

Older schema version:
PermPlaces performs the supported in-place migration.

Newer schema version:
PermPlaces fails closed. Deploy the matching/newer application rather than downgrading and writing
to a database it does not understand.

Application rollback and database rollback remain separate decisions. See
`docs/PRODUCTION.md`.
