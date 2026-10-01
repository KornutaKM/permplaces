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

from app.database import (
    REQUIRED_INDEXES,
    REQUIRED_TABLE_COLUMNS,
    SCHEMA_VERSION,
    favorite_identity_keys_from_payload,
)
from app.notes import MAX_PERSONAL_NOTE_LENGTH
from app.tags import FAVORITE_TAG_KEYS
from app.version import APP_VERSION


class DatabaseAdminError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class DatabaseInspection:
    path: Path
    schema_version: int
    favorites: int | None
    favorite_aliases: int | None
    notes: int | None
    tags: int | None
    ratings: int | None
    provider_budget_rows: int | None


@dataclass(frozen=True, slots=True)
class DatabasePreflight:
    path: Path
    app_version: str
    expected_schema_version: int
    inspection: DatabaseInspection
    missing_tables: tuple[str, ...]
    missing_columns: tuple[str, ...]
    missing_indexes: tuple[str, ...]
    audit: DatabaseAudit | None

    @property
    def status(self) -> str:
        if self.inspection.schema_version > self.expected_schema_version:
            return "schema_newer"
        if self.inspection.schema_version < self.expected_schema_version:
            return "migration_required"
        if self.missing_tables or self.missing_columns or self.missing_indexes:
            return "schema_drift"
        if self.audit is None or not self.audit.consistent:
            return "data_drift"
        return "ok"

    @property
    def ready(self) -> bool:
        return self.status == "ok"


@dataclass(frozen=True, slots=True)
class DatabaseAudit:
    path: Path
    favorites: int
    expected_aliases: int
    actual_aliases: int
    missing_aliases: int
    unexpected_aliases: int
    orphan_aliases: int
    orphan_notes: int | None
    invalid_notes: int | None
    orphan_tags: int | None
    invalid_tags: int | None

    @property
    def aliases_consistent(self) -> bool:
        return (
            self.missing_aliases == 0
            and self.unexpected_aliases == 0
            and self.orphan_aliases == 0
        )

    @property
    def metadata_consistent(self) -> bool:
        return all(
            value in {0, None}
            for value in (
                self.orphan_notes,
                self.invalid_notes,
                self.orphan_tags,
                self.invalid_tags,
            )
        )

    @property
    def consistent(self) -> bool:
        return self.aliases_consistent and self.metadata_consistent


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
                notes=_table_count(connection, "favorite_notes"),
                tags=_table_count(connection, "favorite_tags"),
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


def _existing_schema_objects(
    connection: sqlite3.Connection,
) -> tuple[set[str], set[str]]:
    table_rows = connection.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table'"
    ).fetchall()
    index_rows = connection.execute(
        "SELECT name FROM sqlite_master WHERE type = 'index'"
    ).fetchall()
    tables = {
        str(row[0])
        for row in table_rows
        if row and isinstance(row[0], str)
    }
    indexes = {
        str(row[0])
        for row in index_rows
        if row and isinstance(row[0], str)
    }
    return tables, indexes


def _table_columns_sync(
    connection: sqlite3.Connection,
    table_name: str,
) -> set[str]:
    rows = connection.execute(
        f'PRAGMA table_info("{table_name}")'
    ).fetchall()
    return {
        str(row[1])
        for row in rows
        if len(row) > 1 and isinstance(row[1], str)
    }


def preflight_database(path: str | Path) -> DatabasePreflight:
    inspection = inspect_database(path)
    database_path = inspection.path

    try:
        with closing(_read_only_connection(database_path)) as connection:
            tables, indexes = _existing_schema_objects(connection)
            missing_tables = tuple(
                sorted(set(REQUIRED_TABLE_COLUMNS) - tables)
            )

            missing_columns: list[str] = []
            for table_name, required_columns in REQUIRED_TABLE_COLUMNS.items():
                if table_name not in tables:
                    continue
                actual_columns = _table_columns_sync(connection, table_name)
                missing_columns.extend(
                    f"{table_name}.{column_name}"
                    for column_name in sorted(required_columns - actual_columns)
                )

            missing_indexes = tuple(
                sorted(REQUIRED_INDEXES - indexes)
            )
    except sqlite3.Error as exc:
        raise DatabaseAdminError(
            f"SQLite preflight failed for {database_path}: {exc}"
        ) from exc

    can_audit = (
        inspection.schema_version == SCHEMA_VERSION
        and not missing_tables
        and not missing_columns
    )
    audit = audit_database(database_path) if can_audit else None

    return DatabasePreflight(
        path=database_path,
        app_version=APP_VERSION,
        expected_schema_version=SCHEMA_VERSION,
        inspection=inspection,
        missing_tables=missing_tables,
        missing_columns=tuple(sorted(missing_columns)),
        missing_indexes=missing_indexes,
        audit=audit,
    )


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


def _user_identity_pairs(
    rows: set[tuple[int, str, str]],
) -> set[tuple[int, str]]:
    return {
        (user_id, identity_key)
        for user_id, _venue_id, identity_key in rows
    }


def _metadata_audit_counts(
    connection: sqlite3.Connection,
    *,
    expected_aliases: set[tuple[int, str, str]],
) -> tuple[int | None, int | None, int | None, int | None]:
    expected_identities = _user_identity_pairs(expected_aliases)

    orphan_notes: int | None = None
    invalid_notes: int | None = None
    if _table_count(connection, "favorite_notes") is not None:
        note_rows = connection.execute(
            """
            SELECT user_id, identity_key, note
            FROM favorite_notes
            """
        ).fetchall()
        orphan_notes = 0
        invalid_notes = 0
        for user_id, identity_key, note in note_rows:
            valid_identity = isinstance(user_id, int) and isinstance(identity_key, str)
            if not valid_identity or (user_id, identity_key) not in expected_identities:
                orphan_notes += 1

            if (
                not isinstance(note, str)
                or not note.strip()
                or len(note) > MAX_PERSONAL_NOTE_LENGTH
            ):
                invalid_notes += 1

    orphan_tags: int | None = None
    invalid_tags: int | None = None
    if _table_count(connection, "favorite_tags") is not None:
        allowed_tags = set(FAVORITE_TAG_KEYS)
        tag_rows = connection.execute(
            """
            SELECT user_id, identity_key, tag
            FROM favorite_tags
            """
        ).fetchall()
        orphan_tags = 0
        invalid_tags = 0
        for user_id, identity_key, tag in tag_rows:
            valid_identity = isinstance(user_id, int) and isinstance(identity_key, str)
            if not valid_identity or (user_id, identity_key) not in expected_identities:
                orphan_tags += 1
            if not isinstance(tag, str) or tag not in allowed_tags:
                invalid_tags += 1

    return orphan_notes, invalid_notes, orphan_tags, invalid_tags


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
            (
                orphan_notes,
                invalid_notes,
                orphan_tags,
                invalid_tags,
            ) = _metadata_audit_counts(
                connection,
                expected_aliases=expected,
            )
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
                orphan_notes=orphan_notes,
                invalid_notes=invalid_notes,
                orphan_tags=orphan_tags,
                invalid_tags=invalid_tags,
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
    if not audit.aliases_consistent:
        raise DatabaseAdminError(
            "Alias repair finished but alias consistency audit still reports drift."
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
        help="Check favorite aliases and user metadata consistency without changing data.",
    )
    audit.add_argument("--database", default=_database_default())

    preflight = subparsers.add_parser(
        "preflight",
        help="Run read-only release checks for SQLite schema and application data.",
    )
    preflight.add_argument("--database", default=_database_default())

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
                f"notes={inspection.notes} "
                f"tags={inspection.tags} "
                f"ratings={inspection.ratings} "
                f"provider_budget_rows={inspection.provider_budget_rows}"
            )
            return 0

        if args.command == "preflight":
            preflight = preflight_database(args.database)
            audit = preflight.audit
            print(
                f"preflight_{preflight.status} "
                f"path={preflight.path} "
                f"app_version={preflight.app_version} "
                f"expected_schema_version={preflight.expected_schema_version} "
                f"schema_version={preflight.inspection.schema_version} "
                f"missing_tables={','.join(preflight.missing_tables) or '-'} "
                f"missing_columns={','.join(preflight.missing_columns) or '-'} "
                f"missing_indexes={','.join(preflight.missing_indexes) or '-'} "
                f"audit_consistent={audit.consistent if audit is not None else None} "
                f"missing_aliases={audit.missing_aliases if audit is not None else None} "
                f"unexpected_aliases={audit.unexpected_aliases if audit is not None else None} "
                f"orphan_aliases={audit.orphan_aliases if audit is not None else None} "
                f"orphan_notes={audit.orphan_notes if audit is not None else None} "
                f"invalid_notes={audit.invalid_notes if audit is not None else None} "
                f"orphan_tags={audit.orphan_tags if audit is not None else None} "
                f"invalid_tags={audit.invalid_tags if audit is not None else None}"
            )
            return 0 if preflight.ready else 3

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
                f"orphan_aliases={audit.orphan_aliases} "
                f"orphan_notes={audit.orphan_notes} "
                f"invalid_notes={audit.invalid_notes} "
                f"orphan_tags={audit.orphan_tags} "
                f"invalid_tags={audit.invalid_tags}"
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
