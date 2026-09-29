# Local Docker workflow

PermPlaces uses Docker Compose for the reproducible local runtime.

## Prerequisites

- Git
- Docker Desktop with Docker Compose
- a Telegram bot token from BotFather

## First run on Windows PowerShell

```powershell
git clone https://github.com/KornutaKM/permplaces.git
cd permplaces

Copy-Item .env.example .env
notepad .env
```

Set `BOT_TOKEN` in `.env`. Never commit the token.

Then:

```powershell
docker compose up -d --build
docker compose ps
docker compose logs -f bot
```

The bot uses Telegram long polling, so no host port needs to be published.

The runtime container is intentionally hardened:

- UID/GID `10001:10001` instead of root;
- read-only root filesystem;
- writable named volume only for SQLite data;
- writable tmpfs only for `/tmp`;
- all Linux capabilities dropped;
- `no-new-privileges`;
- bounded CPU, memory and process count.

## Persistent data

Compose stores SQLite in the named volume `permplaces-data`, mounted at:

```text
/app/data
```

The database path inside the container remains:

```text
/app/data/permplaces.db
```

`docker compose down` removes the container/network but keeps the named volume.
`docker compose down -v` also deletes the volume and therefore deletes local favorites.

Before v0.18, local Compose used `./data` as a bind mount. That host directory is not
deleted by this change. If it contains favorites you need to keep, copy the database into
the new named volume before removing the old directory.

## Common commands

Rebuild after code changes:

```powershell
docker compose up -d --build
```

Follow logs:

```powershell
docker compose logs -f bot
```

Stop:

```powershell
docker compose down
```

Inspect status:

```powershell
docker compose ps
```

After initialization the container should report `healthy`. The image healthcheck calls
`/health/ready` inside the container; the health port is not published to the host.

The internal health endpoints are:

- `GET /health/live` — process/event-loop liveness;
- `GET /health/ready` — 200 only after local runtime initialization and SQLite setup;
- readiness returns 503 again before graceful shutdown.

Run a smoke import without starting polling:

```powershell
docker compose run --rm --no-deps bot python -c "import app.main; print('compose-smoke-ok')"
```

## Telegram polling conflict

If logs contain:

```text
Conflict: terminated by other getUpdates request
```

another process is polling Telegram with the same bot token. Only one long-polling instance should run for that token.

Useful checks:

```powershell
docker ps
Get-Process python -ErrorAction SilentlyContinue
```

Stop the duplicate process/container, then restart PermPlaces:

```powershell
docker compose restart bot
```
