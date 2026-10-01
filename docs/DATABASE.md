# SQLite schema and migrations

PermPlaces uses one SQLite database for favorites, community ratings and persistent provider
budget counters.

## Schema version

The application schema is versioned with SQLite `PRAGMA user_version`.

Current version: `4`.

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
adds the separate personal-note table; no existing favorite or rating payload is rewritten. The
v3 → v4 migration adds the separate personal-tag table without rewriting existing favorites,
ratings or notes.

Malformed legacy tables are not silently accepted: startup fails before readiness instead of
pretending that the database is compatible.

## Current tables

Application-owned tables:

- `favorites` — saved venue payloads per Telegram user;
- `favorite_identity_aliases` — exact provider identity keys for indexed favorite lookup;
- `favorite_notes` — private user-authored notes keyed by exact favorite identity;
- `favorite_tags` — private predefined organizational tags keyed by exact favorite identity;
- `venue_ratings` — local 1–5 community ratings;
- `provider_daily_request_budget` — persistent application-side provider request counters.

The indexes `idx_venue_ratings_venue_key`, `idx_favorite_identity_aliases_lookup`,
`idx_favorite_notes_identity_key` and `idx_favorite_tags_identity_key` are part of the schema
contract.

## Operator inspection

The admin CLI can verify SQLite integrity and print only schema/data counters:

```bash
python -m app.db_admin inspect --database data/permplaces.db
```

Example:

```text
inspect_ok path=data/permplaces.db schema_version=4 favorites=12 favorite_aliases=19 notes=7 tags=11 ratings=34 provider_budget_rows=1
```

The command does not print favorite payloads, Telegram user IDs, provider keys, coordinates or
rating rows.

Use `inspect` after a backup/restore drill and before diagnosing schema-related startup failures.
It runs `PRAGMA quick_check` first.

## Release preflight

The target application can run one read-only gate over integrity, schema shape and derived-data
consistency:

```bash
python -m app.db_admin preflight --database data/permplaces.db
```

For a current clean database the command prints `preflight_ok` and exits 0. It checks:

- `PRAGMA quick_check`;
- the installed PermPlaces application version and expected SQLite schema version;
- required application tables and columns;
- required application indexes;
- favorite alias and private note/tag consistency using the same read-only audit contract.

Non-ready states exit with status 3:

- `preflight_migration_required` — the database schema is older than this application;
- `preflight_schema_newer` — the database was written by a newer application;
- `preflight_schema_drift` — the schema version matches but required tables, columns or indexes
  are missing;
- `preflight_data_drift` — schema checks pass but alias/private-metadata audit reports drift.

A migration-required result is not corruption. For a release that intentionally raises
`SCHEMA_VERSION`, create and verify the pre-migration backup before allowing startup migration.
A schema-newer result is a fail-closed application mismatch: deploy the matching/newer application
instead of writing with the older one.

The command does not migrate, rebuild indexes, repair aliases or delete user metadata. Output is
limited to versions, schema object names and aggregate audit counters; it does not print user IDs,
favorite payloads, note text, tag rows or provider credentials.

## Favorite and user-metadata consistency audit

Schema v2+ treats `favorite_identity_aliases` as a derived index of `favorites`. Schema v3/v4
also stores private notes/tags keyed by the same exact identities. Operators can verify these
relationships without printing user IDs, venue payloads, note text, tag rows or identity keys:

```bash
python -m app.db_admin audit --database data/permplaces.db
```

A consistent current database prints `audit_ok` and zero counts for missing/unexpected/orphan
alias rows, orphan/invalid notes and orphan/invalid tags. Drift prints `audit_drift` and exits
with status 3.

Metadata attachment is checked against identities derived directly from favorite payloads, not
against the potentially drifted alias index. This prevents an unexpected alias row from making an
orphan note or tag appear valid. For older schemas where `favorite_notes` or `favorite_tags`
does not exist yet, the corresponding counters are reported as `None` rather than treated as
drift.

The audit is read-only. If drift must be repaired, stop the bot and run:

```bash
python -m app.db_admin repair-aliases \
  --database data/permplaces.db \
  --confirm-stopped
```

Repair creates a timestamped `pre-alias-repair` safety backup, rebuilds the alias index only from
the exact provider identities already stored in favorite payloads, runs `quick_check`, and then
requires the alias portion of the audit to be clean. It does not change favorite payloads,
community ratings, personal notes or personal tags.

`repair-aliases` deliberately does not delete or rewrite orphan/invalid user metadata. Such drift
requires operator investigation or restoration from a known-good backup because PermPlaces will
not guess which favorite user-authored content belonged to.

## Backward and forward compatibility

Older schema version:
PermPlaces performs the supported in-place migration.

Newer schema version:
PermPlaces fails closed. Deploy the matching/newer application rather than downgrading and writing
to a database it does not understand.

Application rollback and database rollback remain separate decisions. After a schema v4 migration,
v0.35 and older applications intentionally refuse the newer database. Rolling the application back
across this boundary therefore also requires an explicitly selected pre-migration database backup.
See `docs/PRODUCTION.md`.
