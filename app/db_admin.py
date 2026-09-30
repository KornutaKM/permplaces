from __future__ import annotations

import argparse
import os
import shutil
import sqlite3
import tempfile
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path


class DatabaseAdminError(RuntimeError):
    pass


def _read_only_connection(path: Path) -> sqlite3.Connection:
    uri = path.resolve().as_uri() + "?mode=ro"
    return sqlite3.connect(uri, uri=True)


def _quick_check(connection: sqlite3.Connection) -> tuple[str, ...]:
    rows = connection.execute("PRAGMA quick_check").fetchall()
    return tuple(str(row[0]) for row in rows if row)


def verify_database(path: str | Path) -> Path:
    database_path = Path(path)
    if not database_path.is_file():
        raise DatabaseAdminError(f"Database file does not exist: {database_path}")

    try:
        with closing(_read_only_connection(database_path)) as connection:
            result = _quick_check(connection)
    except sqlite3.Error as exc:
        raise DatabaseAdminError(
            f"SQLite verification failed for {database_path}: {exc}"
        ) from exc

    if result != ("ok",):
        details = "; ".join(result) if result else "no quick_check result"
        raise DatabaseAdminError(
            f"SQLite quick_check failed for {database_path}: {details}"
        )

    return database_path


def backup_database(
    source: str | Path,
    destination: str | Path,
    *,
    overwrite: bool = False,
) -> Path:
    source_path = verify_database(source)
    destination_path = Path(destination)

    if destination_path.exists() and not overwrite:
        raise DatabaseAdminError(
            f"Backup destination already exists: {destination_path}"
        )

    destination_path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{destination_path.name}.",
        suffix=".tmp",
        dir=destination_path.parent,
    )
    os.close(descriptor)
    temporary_path = Path(temporary_name)

    try:
        with closing(_read_only_connection(source_path)) as source_connection:
            with closing(sqlite3.connect(temporary_path)) as backup_connection:
                source_connection.backup(backup_connection)
                result = _quick_check(backup_connection)
                if result != ("ok",):
                    details = "; ".join(result) if result else "no quick_check result"
                    raise DatabaseAdminError(
                        f"Backup quick_check failed: {details}"
                    )

        os.replace(temporary_path, destination_path)
    except Exception:
        temporary_path.unlink(missing_ok=True)
        raise

    return destination_path


def _restore_snapshot_path(database_path: Path) -> Path:
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    suffix = database_path.suffix or ".db"
    return database_path.with_name(
        f"{database_path.stem}.pre-restore-{timestamp}{suffix}"
    )


def restore_database(
    backup: str | Path,
    database: str | Path,
    *,
    confirm_stopped: bool,
) -> Path | None:
    if not confirm_stopped:
        raise DatabaseAdminError(
            "Restore refused: stop the bot first and pass --confirm-stopped."
        )

    backup_path = verify_database(backup)
    database_path = Path(database)
    database_path.parent.mkdir(parents=True, exist_ok=True)

    safety_backup: Path | None = None
    if database_path.exists():
        safety_backup = _restore_snapshot_path(database_path)
        backup_database(database_path, safety_backup)

    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{database_path.name}.restore.",
        suffix=".tmp",
        dir=database_path.parent,
    )
    os.close(descriptor)
    temporary_path = Path(temporary_name)

    try:
        shutil.copy2(backup_path, temporary_path)
        verify_database(temporary_path)

        for sidecar_suffix in ("-wal", "-shm"):
            Path(f"{database_path}{sidecar_suffix}").unlink(missing_ok=True)

        os.replace(temporary_path, database_path)
        verify_database(database_path)
    except Exception:
        temporary_path.unlink(missing_ok=True)
        raise

    return safety_backup


def _database_default() -> str:
    return os.getenv("DATABASE_PATH", "data/permplaces.db")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Safe SQLite backup, verification and offline restore helpers."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    backup = subparsers.add_parser("backup", help="Create a consistent SQLite backup.")
    backup.add_argument("--database", default=_database_default())
    backup.add_argument("--output", required=True)
    backup.add_argument("--overwrite", action="store_true")

    verify = subparsers.add_parser("verify", help="Run SQLite quick_check.")
    verify.add_argument("--database", required=True)

    restore = subparsers.add_parser(
        "restore",
        help="Restore a verified backup after the bot has been stopped.",
    )
    restore.add_argument("--database", default=_database_default())
    restore.add_argument("--input", required=True)
    restore.add_argument(
        "--confirm-stopped",
        action="store_true",
        help="Required acknowledgement that no bot process is using the database.",
    )

    return parser


def main() -> int:
    args = _parser().parse_args()

    try:
        if args.command == "backup":
            output = backup_database(
                args.database,
                args.output,
                overwrite=args.overwrite,
            )
            print(f"backup_ok path={output}")
            return 0

        if args.command == "verify":
            database = verify_database(args.database)
            print(f"verify_ok path={database}")
            return 0

        if args.command == "restore":
            safety_backup = restore_database(
                args.input,
                args.database,
                confirm_stopped=args.confirm_stopped,
            )
            print(f"restore_ok path={args.database}")
            if safety_backup is not None:
                print(f"pre_restore_backup={safety_backup}")
            return 0
    except DatabaseAdminError as exc:
        print(f"database_admin_error: {exc}")
        return 2

    raise AssertionError(f"Unsupported command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
