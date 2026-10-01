# SQLite schema and migrations

PermPlaces uses one SQLite database for favorites, community ratings and persistent provider
budget counters.

## Schema version

The application schema is versioned with SQLite `PRAGMA user_version`.

Current version: `3`.

Startup calls one central `initialize_database()` function before Telegram polling begins. The
initializer:

- enables WAL mode;
- takes an immediate migration transaction;
- creates missing application tables and indexes;
- validates required columns on existing tables;
- refuses to run if the database schema version is newer than the application;
- updates `PRAGMA user_version` only after validation succeeds.

Databases created by earlier PermPlaces versions are upgraded in place without deleting existing
favorites or community ratings. The v1 → v2 migration creates the favorite identity alias index
and backfills it from each stored favorite payload. If a historical payload cannot be decoded, its
existing `venue_id` is still indexed as a conservative fallback identity. The v2 → v3 migration
adds the separate personal-note table; no existing favorite or rating payload is rewritten.

Malformed legacy tables are not silently accepted: startup fails before readiness instead of
pretending that the database is compatible.

## Current tables

Application-owned tables:

- `favorites` — saved venue payloads per Telegram user;
- `favorite_identity_aliases` — exact provider identity keys for indexed favorite lookup;
- `favorite_notes` — private user-authored notes keyed by exact favorite identity;
- `venue_ratings` — local 1–5 community ratings;
- `provider_daily_request_budget` — persistent application-side provider request counters.

The indexes `idx_venue_ratings_venue_key`, `idx_favorite_identity_aliases_lookup` and
`idx_favorite_notes_identity_key` are part of the schema contract.

## Operator inspection

The admin CLI can verify SQLite integrity and print only schema/data counters:

```bash
python -m app.db_admin inspect --database data/permplaces.db
```

Example:

```text
inspect_ok path=data/permplaces.db schema_version=3 favorites=12 favorite_aliases=19 notes=7 ratings=34 provider_budget_rows=1
```

The command does not print favorite payloads, Telegram user IDs, provider keys, coordinates or
rating rows.

Use `inspect` after a backup/restore drill and before diagnosing schema-related startup failures.
It runs `PRAGMA quick_check` first.

## Favorite alias consistency audit

Schema v2 treats `favorite_identity_aliases` as a derived index of `favorites`. Operators can
verify that relationship without printing user IDs, venue payloads or identity keys:

```bash
python -m app.db_admin audit --database data/permplaces.db
```

A consistent database prints `audit_ok` and zero counts for missing, unexpected and orphan alias
rows. Drift prints `audit_drift` and exits with status 3.

The audit is read-only. If drift must be repaired, stop the bot and run:

```bash
python -m app.db_admin repair-aliases \
  --database data/permplaces.db \
  --confirm-stopped
```

Repair creates a timestamped `pre-alias-repair` safety backup, rebuilds the alias index only from
the exact provider identities already stored in favorite payloads, runs `quick_check`, and then
requires a clean audit. It does not change favorite payloads or community ratings.

## Backward and forward compatibility

Older schema version:
PermPlaces performs the supported in-place migration.

Newer schema version:
PermPlaces fails closed. Deploy the matching/newer application rather than downgrading and writing
to a database it does not understand.

Application rollback and database rollback remain separate decisions. After a schema v3 migration,
v0.34 and older applications intentionally refuse the newer database. Rolling the application back
across this boundary therefore also requires an explicitly selected pre-migration database backup.
See `docs/PRODUCTION.md`.
