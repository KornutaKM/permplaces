# PermPlaces production runbook

This runbook defines the current production contract for the Docker Compose deployment profile.
It intentionally stays host-agnostic: the repository does not assume a specific cloud vendor,
VM provider, reverse proxy or secret manager.

## 1. Production assumptions

- one active Telegram polling instance per bot token;
- Docker Engine with Docker Compose v2;
- the repository is deployed from an exact reviewed `main` commit;
- SQLite lives in the `permplaces-data` named volume at `/app/data/permplaces.db`;
- the container keeps its hardened runtime profile: non-root UID/GID 10001, read-only root
  filesystem, dropped Linux capabilities and `no-new-privileges`;
- health is internal to the Compose network and must not be exposed publicly just to monitor it.

Running two bot containers with the same Telegram token is not an HA strategy. Telegram long
polling will reject concurrent `getUpdates` consumers.

## 2. Secrets

Create the production env file from the committed template:

```bash
cp .env.example .env
```

Set at minimum:

```env
BOT_TOKEN=...
```

Optional provider keys remain opt-in:

```env
GEOAPIFY_API_KEY=
GEOAPIFY_DAILY_REQUEST_BUDGET=2500
TWOGIS_API_KEY=
FOURSQUARE_API_KEY=
```

Rules:

- never commit `.env`;
- do not paste tokens into issue/PR comments or CI logs;
- on a Linux host, restrict the file to the deployment account:

  ```bash
  chmod 600 .env
  ```

- if a token is exposed, rotate it at the provider and update the host secret before restarting;
- keep the operator-controlled Overpass fallback list explicit. Do not silently add operators.

## 3. Pre-deploy gate

Before every production change:

```bash
git fetch origin
git checkout main
git pull --ff-only
git rev-parse HEAD
docker compose config --quiet
```

Confirm in GitHub that the exact `main` commit passed the repository CI. Do not deploy from an
unreviewed local working tree.

Record the current production SHA before changing it:

```bash
git rev-parse HEAD > .production-previous-sha
```

If a previous `permplaces:local` image exists, keep a rollback tag before rebuilding:

```bash
PREVIOUS_SHA="$(cat .production-previous-sha)"
docker image inspect permplaces:local >/dev/null 2>&1 &&   docker image tag permplaces:local "permplaces:rollback-$PREVIOUS_SHA"
```

## 4. Deploy

For a release that raises the SQLite schema version, create and copy a verified database backup
**before** starting the new image. The migration runs during startup, so the pre-migration backup
is the rollback boundary for the database. v0.32 raises the schema from 1 to 2.

Do not assume that an older application image can open a migrated database: PermPlaces rejects a
database whose schema version is newer than the running application.

Build and replace only the bot service:

```bash
docker compose build --pull bot
docker compose up -d --no-deps bot
```

Verify:

```bash
docker compose ps
docker compose logs --since=5m bot
```

The bot should become `healthy`. The runtime must not show repeated Telegram
`Conflict: terminated by other getUpdates request` errors. If it does, locate and stop the other
polling instance instead of retrying both.

A direct readiness probe can be executed inside the container:

```bash
docker compose exec bot python -c \
  'import os, urllib.request; print(urllib.request.urlopen("http://127.0.0.1:" + os.getenv("HEALTH_PORT", "8080") + "/health/ready", timeout=2).status)'
```

Expected result: `200`.

## 5. SQLite backup

PermPlaces uses WAL mode. Do not copy only the live `.db` file with a filesystem command while
the bot is running. Use the SQLite backup API exposed by `app.db_admin`.

Create a consistent backup while the bot is running:

```bash
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
docker compose exec bot mkdir -p /app/data/backups
docker compose exec bot python -m app.db_admin backup \
  --database /app/data/permplaces.db \
  --output "/app/data/backups/permplaces-$STAMP.db"
docker compose exec bot python -m app.db_admin verify \
  --database "/app/data/backups/permplaces-$STAMP.db"
docker compose exec bot python -m app.db_admin inspect \
  --database "/app/data/backups/permplaces-$STAMP.db"
mkdir -p backups
docker compose cp \
  "bot:/app/data/backups/permplaces-$STAMP.db" \
  "./backups/permplaces-$STAMP.db"
```

The same SQLite backup also contains community ratings and the persistent provider budget counters.

User-triggered `/mydata` deletion removes live favorites and ratings from the application
database, but it does not rewrite older backup files. Backup retention/deletion remains an
operator responsibility; see `docs/PRIVACY.md`.

Keep copied backups outside the Docker host as part of the operator's normal backup policy.
The repository intentionally does not prescribe a storage vendor.

The backup command refuses to overwrite an existing destination unless `--overwrite` is passed.

## 6. Restore drill and production restore

A restore is an offline operation. The admin command refuses to restore unless the operator passes
`--confirm-stopped`.

First verify the backup in an isolated one-off container:

```bash
docker compose run --rm --no-deps \
  -v "$PWD/backups:/backup:ro" \
  bot python -m app.db_admin verify \
  --database /backup/permplaces-YYYYMMDDTHHMMSSZ.db
docker compose run --rm --no-deps \
  -v "$PWD/backups:/backup:ro" \
  bot python -m app.db_admin inspect \
  --database /backup/permplaces-YYYYMMDDTHHMMSSZ.db
```

Create one final live backup, then stop the bot:

```bash
docker compose stop bot
```

Restore:

```bash
docker compose run --rm --no-deps \
  -v "$PWD/backups:/backup:ro" \
  bot python -m app.db_admin restore \
  --database /app/data/permplaces.db \
  --input /backup/permplaces-YYYYMMDDTHHMMSSZ.db \
  --confirm-stopped
```

If a database already existed, the restore command creates and prints a
`permplaces.pre-restore-<UTC timestamp>.db` safety snapshot in the data volume before replacing
the live database. It also removes stale `-wal` and `-shm` sidecars before installing the
verified backup.

Start and verify:

```bash
docker compose up -d --no-deps bot
docker compose ps
docker compose logs --since=5m bot
```

A restore drill is successful only when `db_admin inspect` reports the expected schema version/counters, the bot becomes healthy, and expected favorites and community ratings can be read after restart. Run a drill before the first production launch and after material storage
changes.

## 7. Application rollback

If the new application build is unhealthy but the database is still valid, roll back the
application without restoring data.

Preferred path when a rollback image was tagged:

```bash
PREVIOUS_SHA="$(cat .production-previous-sha)"
docker image tag "permplaces:rollback-$PREVIOUS_SHA" permplaces:local
docker compose up -d --no-deps --no-build bot
docker compose ps
```

Otherwise check out the exact previous reviewed SHA and rebuild:

```bash
PREVIOUS_SHA="$(cat .production-previous-sha)"
git checkout "$PREVIOUS_SHA"
docker compose build bot
docker compose up -d --no-deps bot
```

After recovery, return the repository checkout to `main` before the next deployment.

Database restore is a separate decision. Do not restore an older SQLite backup merely because an
application rollback was required. The exception is an intentional rollback across an incompatible
schema boundary: for example, v0.31 cannot open a schema-v2 database created by v0.32, so that
rollback requires the matching pre-migration backup selected by the operator.

## 8. Failure checklist

If readiness stays unhealthy:

1. inspect `docker compose logs --since=10m bot`;
2. confirm `.env` contains a valid `BOT_TOKEN`;
3. confirm the named volume is mounted and writable by UID 10001;
4. confirm there is only one polling instance for the token;
5. check provider failures separately from core bot startup; optional Geoapify/2GIS/Foursquare keys are not
   required for the base OSM flow;
6. if SQLite initialization fails, run `python -m app.db_admin verify` and `python -m app.db_admin inspect` before considering a restore; a database newer than the application must not be downgraded in place.

Do not delete `permplaces-data` during routine troubleshooting. In particular,
`docker compose down -v` destroys the named volume and therefore the live favorites and community-ratings database.

## 9. Release evidence

For every production release keep, at minimum:

- deployed Git commit SHA;
- GitHub CI run for that exact reviewed change;
- UTC deployment time;
- backup filename created before a risky storage operation;
- result of the readiness check;
- rollback SHA/image tag retained until the release is accepted.
