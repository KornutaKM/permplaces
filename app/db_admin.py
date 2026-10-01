from __future__ import annotations

import argparse
import os
import shutil
import sqlite3
import tempfile
from contextlib import closing
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from app.database import favorite_identity_keys_from_payload


class DatabaseAdminError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class DatabaseInspection:
    path: Path
    schema_version: int
    favorites: int | None
    favorite_aliases: int | None
    ratings: int | None
    provider_budget_rows: int | None


@dataclass(frozen=True, slots=True)
class DatabaseAudit:
    path: Path
    favorites: int
    expected_aliases: int
    actual_aliases: int
    missing_aliases: int
    unexpected_aliases: int
    orphan_aliases: int

    @property
    def consistent(self) -> bool:
        return (
            self.missing_aliases == 0
            and self.unexpected_aliases == 0
            and self.orphan_aliases == 0
        )


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


def _table_count(
    connection: sqlite3.Connection,
    table_name: str,
) -> int | None:
    row = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table_name,),
    ).fetchone()
    if row is None:
        return None
    count_row = connection.execute(
        f'SELECT COUNT(*) FROM "{table_name}"'
    ).fetchone()
    return int(count_row[0]) if count_row is not None else 0


def inspect_database(path: str | Path) -> DatabaseInspection:
    database_path = verify_database(path)
    try:
        with closing(_read_only_connection(database_path)) as connection:
            version_row = connection.execute("PRAGMA user_version").fetchone()
            schema_version = int(version_row[0]) if version_row else 0
            return DatabaseInspection(
                path=database_path,
                schema_version=schema_version,
                favorites=_table_count(connection, "favorites"),
                favorite_aliases=_table_count(
                    connection,
                    "favorite_identity_aliases",
                ),
                ratings=_table_count(connection, "venue_ratings"),
                provider_budget_rows=_table_count(
                    connection,
                    "provider_daily_request_budget",
                ),
            )
    except sqlite3.Error as exc:
        raise DatabaseAdminError(
            f"SQLite inspection failed for {database_path}: {exc}"
        ) from exc


def _favorite_alias_sets(
    connection: sqlite3.Connection,
) -> tuple[
    set[tuple[int, str, str]],
    set[tuple[int, str, str]],
    set[tuple[int, str]],
]:
    favorite_rows = connection.execute(
        """
        SELECT user_id, venue_id, payload
        FROM favorites
        """
    ).fetchall()
    expected: set[tuple[int, str, str]] = set()
    favorite_ids: set[tuple[int, str]] = set()

    for user_id, venue_id, payload in favorite_rows:
        if not isinstance(user_id, int):
            continue
        if not isinstance(venue_id, str) or not isinstance(payload, str):
            continue
        favorite_ids.add((user_id, venue_id))
        for identity_key in favorite_identity_keys_from_payload(venue_id, payload):
            expected.add((user_id, venue_id, identity_key))

    alias_rows = connection.execute(
        """
        SELECT user_id, venue_id, identity_key
        FROM favorite_identity_aliases
        """
    ).fetchall()
    actual = {
        (user_id, venue_id, identity_key)
        for user_id, venue_id, identity_key in alias_rows
        if isinstance(user_id, int)
        and isinstance(venue_id, str)
        and isinstance(identity_key, str)
    }
    return expected, actual, favorite_ids


def audit_database(path: str | Path) -> DatabaseAudit:
    database_path = verify_database(path)
    try:
        with closing(_read_only_connection(database_path)) as connection:
            expected, actual, favorite_ids = _favorite_alias_sets(connection)
            missing = expected - actual
            unexpected = actual - expected
            orphan = {
                row
                for row in actual
                if (row[0], row[1]) not in favorite_ids
            }
            favorite_count = _table_count(connection, "favorites")
            if favorite_count is None:
                raise DatabaseAdminError(
                    "Database audit requires the favorites table."
                )
            return DatabaseAudit(
                path=database_path,
                favorites=favorite_count,
                expected_aliases=len(expected),
                actual_aliases=len(actual),
                missing_aliases=len(missing),
                unexpected_aliases=len(unexpected),
                orphan_aliases=len(orphan),
            )
    except sqlite3.Error as exc:
        raise DatabaseAdminError(
            f"SQLite audit failed for {database_path}: {exc}"
        ) from exc


def _repair_snapshot_path(database_path: Path) -> Path:
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    suffix = database_path.suffix or ".db"
    return database_path.with_name(
        f"{database_path.stem}.pre-alias-repair-{timestamp}{suffix}"
    )


def repair_favorite_aliases(
    database: str | Path,
    *,
    confirm_stopped: bool,
) -> Path:
    if not confirm_stopped:
        raise DatabaseAdminError(
            "Alias repair refused: stop the bot first and pass --confirm-stopped."
        )

    database_path = verify_database(database)
    safety_backup = _repair_snapshot_path(database_path)
    backup_database(database_path, safety_backup)

    try:
        with closing(sqlite3.connect(database_path)) as connection:
            connection.execute("PRAGMA busy_timeout=5000")
            connection.execute("BEGIN IMMEDIATE")
            try:
                connection.execute("DELETE FROM favorite_identity_aliases")
                rows = connection.execute(
                    """
                    SELECT user_id, venue_id, payload
                    FROM favorites
                    ORDER BY user_id, created_at, venue_id
                    """
                ).fetchall()

                for user_id, venue_id, payload in rows:
                    if not isinstance(user_id, int):
                        continue
                    if not isinstance(venue_id, str) or not isinstance(payload, str):
                        continue
                    for identity_key in favorite_identity_keys_from_payload(
                        venue_id,
                        payload,
                    ):
                        connection.execute(
                            """
                            INSERT OR IGNORE INTO favorite_identity_aliases (
                                user_id,
                                venue_id,
                                identity_key
                            )
                            VALUES (?, ?, ?)
                            """,
                            (user_id, venue_id, identity_key),
                        )
                connection.commit()
            except BaseException:
                connection.rollback()
                raise
    except sqlite3.Error as exc:
        raise DatabaseAdminError(
            f"SQLite alias repair failed for {database_path}: {exc}"
        ) from exc

    verify_database(database_path)
    audit = audit_database(database_path)
    if not audit.consistent:
        raise DatabaseAdminError(
            "Alias repair finished but consistency audit still reports drift."
        )
    return safety_backup


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
        with (
            closing(_read_only_connection(source_path)) as source_connection,
            closing(sqlite3.connect(temporary_path)) as backup_connection,
        ):
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

    inspect_parser = subparsers.add_parser(
        "inspect",
        help="Verify SQLite and print schema/data counters without row contents.",
    )
    inspect_parser.add_argument("--database", default=_database_default())

    audit = subparsers.add_parser(
        "audit",
        help="Check favorite identity alias consistency without changing data.",
    )
    audit.add_argument("--database", default=_database_default())

    repair = subparsers.add_parser(
        "repair-aliases",
        help="Rebuild the derived favorite identity alias index offline.",
    )
    repair.add_argument("--database", default=_database_default())
    repair.add_argument(
        "--confirm-stopped",
        action="store_true",
        help="Required acknowledgement that no bot process is using the database.",
    )

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

        if args.command == "inspect":
            inspection = inspect_database(args.database)
            print(
                "inspect_ok "
                f"path={inspection.path} "
                f"schema_version={inspection.schema_version} "
                f"favorites={inspection.favorites} "
                f"favorite_aliases={inspection.favorite_aliases} "
                f"ratings={inspection.ratings} "
                f"provider_budget_rows={inspection.provider_budget_rows}"
            )
            return 0

        if args.command == "audit":
            audit = audit_database(args.database)
            status = "audit_ok" if audit.consistent else "audit_drift"
            print(
                f"{status} "
                f"path={audit.path} "
                f"favorites={audit.favorites} "
                f"expected_aliases={audit.expected_aliases} "
                f"actual_aliases={audit.actual_aliases} "
                f"missing_aliases={audit.missing_aliases} "
                f"unexpected_aliases={audit.unexpected_aliases} "
                f"orphan_aliases={audit.orphan_aliases}"
            )
            return 0 if audit.consistent else 3

        if args.command == "repair-aliases":
            safety_backup = repair_favorite_aliases(
                args.database,
                confirm_stopped=args.confirm_stopped,
            )
            print(
                f"repair_aliases_ok path={args.database} "
                f"pre_repair_backup={safety_backup}"
            )
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
