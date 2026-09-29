# SQLite backup and restore runbook

PermPlaces stores user favorites in SQLite at `/app/data/permplaces.db`.

The Compose deployment keeps `/app/data` in the named volume `permplaces-data`.

## Safety rules

- Creating a backup is safe while the bot is running. It uses SQLite's online backup API.
- Every created backup is checked with `PRAGMA integrity_check` before it is accepted.
- Restore is destructive when the target database already exists and therefore requires `--force`.
- Stop the bot before restore. The CLI cannot prove that no other process has the database open.
- Restore removes stale `-wal` and `-shm` sidecars before atomically replacing the database.
- Never use `docker compose down -v` unless deleting the local database is intentional.

## Create a backup

With the normal bot container running:

```powershell
docker compose run --rm --no-deps bot python -m app.backup create `
  --database /app/data/permplaces.db `
  --output /app/data/backups/permplaces.db
```

The backup is created inside the persistent Docker volume.

To replace an existing backup deliberately:

```powershell
docker compose run --rm --no-deps bot python -m app.backup create `
  --database /app/data/permplaces.db `
  --output /app/data/backups/permplaces.db `
  --force
```

## Verify a backup

```powershell
docker compose run --rm --no-deps bot python -m app.backup verify `
  --input /app/data/backups/permplaces.db
```

A successful command prints:

```text
backup_verified=/app/data/backups/permplaces.db
```

## Copy a backup to the host

When the bot service is running:

```powershell
New-Item -ItemType Directory -Force .\backups
docker compose cp bot:/app/data/backups/permplaces.db .\backups\permplaces.db
```

Keep off-machine copies according to your own retention policy.

## Restore from a backup already in the volume

Stop polling first:

```powershell
docker compose stop bot
```

Verify:

```powershell
docker compose run --rm --no-deps bot python -m app.backup verify `
  --input /app/data/backups/permplaces.db
```

Restore:

```powershell
docker compose run --rm --no-deps bot python -m app.backup restore `
  --input /app/data/backups/permplaces.db `
  --database /app/data/permplaces.db `
  --force
```

Restart and inspect health/logs:

```powershell
docker compose up -d bot
docker compose ps
docker compose logs --tail=100 bot
```

## Restore drill

A backup is not operationally useful until restore has been tested.

Recommended drill:

1. create a fresh backup;
2. verify it;
3. stop the bot;
4. restore it with `--force`;
5. restart the bot;
6. confirm the container returns to `healthy`;
7. open Telegram and verify saved favorites are present;
8. record the drill date and the backup artifact used.

## CLI outside Docker

The same commands work in a Python environment:

```powershell
python -m app.backup create --database data/permplaces.db --output backup.db
python -m app.backup verify --input backup.db
python -m app.backup restore --input backup.db --database data/permplaces.db --force
```

The default database path follows `DATABASE_PATH` or falls back to `data/permplaces.db`.