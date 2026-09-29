from __future__ import annotations

import argparse
import os
import sqlite3
import sys
from pathlib import Path


class BackupError(RuntimeError):
    """Raised when a backup or restore operation cannot be trusted."""


def verify_database(path: str | Path) -> Path:
    database_path = Path(path)
    if not database_path.is_file():
        raise FileNotFoundError(database_path)

    try:
        with sqlite3.connect(database_path) as database:
            row = database.execute("PRAGMA integrity_check").fetchone()
    except sqlite3.DatabaseError as exc:
        raise BackupError(f"SQLite integrity check failed for {database_path}") from exc

    if row is None or row[0] != "ok":
        detail = row[0] if row else "no result"
        raise BackupError(
            f"SQLite integrity check failed for {database_path}: {detail}"
        )

    return database_path


def _temporary_path(target: Path, operation: str) -> Path:
    return target.with_name(f".{target.name}.{operation}.tmp")


def _remove_if_exists(path: Path) -> None:
    try:
        path.unlink()
    except FileNotFoundError:
        pass


def create_backup(
    database_path: str | Path,
    output_path: str | Path,
    *,
    overwrite: bool = False,
) -> Path:
    source = Path(database_path)
    output = Path(output_path)

    if not source.is_file():
        raise FileNotFoundError(source)
    if output.exists() and not overwrite:
        raise FileExistsError(output)

    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = _temporary_path(output, "backup")
    _remove_if_exists(temporary)

    try:
        with sqlite3.connect(source) as source_db:
            with sqlite3.connect(temporary) as backup_db:
                source_db.backup(backup_db)

        verify_database(temporary)
        os.replace(temporary, output)
    finally:
        _remove_if_exists(temporary)

    return output


def restore_backup(
    backup_path: str | Path,
    database_path: str | Path,
    *,
    overwrite: bool = False,
) -> Path:
    backup = verify_database(backup_path)
    target = Path(database_path)

    if target.exists() and not overwrite:
        raise FileExistsError(target)

    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = _temporary_path(target, "restore")
    _remove_if_exists(temporary)

    try:
        with sqlite3.connect(backup) as source_db:
            with sqlite3.connect(temporary) as restored_db:
                source_db.backup(restored_db)

        verify_database(temporary)

        if overwrite:
            _remove_if_exists(Path(f"{target}-wal"))
            _remove_if_exists(Path(f"{target}-shm"))

        os.replace(temporary, target)
    finally:
        _remove_if_exists(temporary)

    return target


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Create, verify, or restore PermPlaces SQLite backups."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    default_database = os.getenv("DATABASE_PATH", "data/permplaces.db")

    create = subparsers.add_parser("create", help="Create a verified SQLite backup.")
    create.add_argument("--database", default=default_database)
    create.add_argument("--output", required=True)
    create.add_argument("--force", action="store_true")

    verify = subparsers.add_parser("verify", help="Run SQLite integrity_check.")
    verify.add_argument("--input", required=True)

    restore = subparsers.add_parser("restore", help="Restore a verified SQLite backup.")
    restore.add_argument("--input", required=True)
    restore.add_argument("--database", default=default_database)
    restore.add_argument("--force", action="store_true")

    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)

    try:
        if args.command == "create":
            path = create_backup(
                args.database,
                args.output,
                overwrite=args.force,
            )
            print(f"backup_created={path}")
        elif args.command == "verify":
            path = verify_database(args.input)
            print(f"backup_verified={path}")
        elif args.command == "restore":
            path = restore_backup(
                args.input,
                args.database,
                overwrite=args.force,
            )
            print(f"backup_restored={path}")
        else:
            raise AssertionError(f"unsupported command: {args.command}")
    except (BackupError, FileExistsError, FileNotFoundError, OSError) as exc:
        print(f"backup_error={exc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
