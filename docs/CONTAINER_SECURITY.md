# Container security contract

PermPlaces runs as a long-lived network client and should not require root privileges.

## Identity

The production image creates and runs as:

```text
uid=10001
gid=10001
```

CI blocks regressions back to UID 0.

## Filesystem

The root filesystem is read-only in Compose.

Writable locations are intentionally limited to:

- `/app/data` — Docker named volume for SQLite;
- `/tmp` — bounded tmpfs for runtime temporary files.

Application code, installed packages and configuration inside the image are not writable by
the bot process.

## Linux privilege surface

Compose applies:

```yaml
security_opt:
  - no-new-privileges:true
cap_drop:
  - ALL
```

PermPlaces does not need privileged ports, raw sockets, filesystem mounts or other Linux
capabilities.

## Resource bounds

The default local/production-shaped Compose profile sets:

- CPU: 1.0
- memory: 256 MiB
- PID limit: 128
- tmpfs: 16 MiB

These are safety defaults, not performance claims. They can be revisited after measured load
testing.

## Persistent data

SQLite lives in the named volume `permplaces-data`. Normal `docker compose down` preserves
it. `docker compose down -v` is destructive.

The previous pre-v0.18 `./data` bind-mounted directory is not automatically deleted or
migrated.

## CI assertions

The Docker CI lane verifies:

1. Compose config is valid.
2. Image healthcheck targets `/health/ready`.
3. Image declares user `10001:10001`.
4. Runtime UID is 10001.
5. `/app/data` is writable.
6. writing to `/app` fails under the read-only root filesystem.
7. the Python application imports successfully in the hardened runtime.
