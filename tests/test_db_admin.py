import sqlite3
from pathlib import Path

import pytest

from app.db_admin import (
    DatabaseAdminError,
    backup_database,
    inspect_database,
    restore_database,
    verify_database,
)


def _create_database(path: Path, value: str) -> None:
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE state (value TEXT NOT NULL)")
        connection.execute("INSERT INTO state(value) VALUES (?)", (value,))
        connection.commit()


def _read_value(path: Path) -> str:
    with sqlite3.connect(path) as connection:
        row = connection.execute("SELECT value FROM state").fetchone()
    assert row is not None
    return str(row[0])


def test_backup_uses_consistent_sqlite_snapshot_with_wal(tmp_path: Path) -> None:
    database = tmp_path / "permplaces.db"
    backup = tmp_path / "backups" / "permplaces.db"

    connection = sqlite3.connect(database)
    try:
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("CREATE TABLE state (value TEXT NOT NULL)")
        connection.execute("INSERT INTO state(value) VALUES ('live')")
        connection.commit()

        created = backup_database(database, backup)
    finally:
        connection.close()

    assert created == backup
    assert verify_database(backup) == backup
    assert _read_value(backup) == "live"


def test_backup_refuses_to_overwrite_existing_file_by_default(
    tmp_path: Path,
) -> None:
    database = tmp_path / "permplaces.db"
    backup = tmp_path / "backup.db"
    _create_database(database, "live")
    _create_database(backup, "existing")

    with pytest.raises(DatabaseAdminError, match="already exists"):
        backup_database(database, backup)

    assert _read_value(backup) == "existing"


def test_verify_rejects_non_database_file(tmp_path: Path) -> None:
    corrupt = tmp_path / "corrupt.db"
    corrupt.write_text("not sqlite", encoding="utf-8")

    with pytest.raises(DatabaseAdminError, match="verification failed"):
        verify_database(corrupt)


def test_restore_requires_explicit_stopped_confirmation(tmp_path: Path) -> None:
    database = tmp_path / "permplaces.db"
    backup = tmp_path / "backup.db"
    _create_database(database, "old")
    _create_database(backup, "new")

    with pytest.raises(DatabaseAdminError, match="confirm-stopped"):
        restore_database(backup, database, confirm_stopped=False)

    assert _read_value(database) == "old"


def test_restore_keeps_pre_restore_snapshot_and_replaces_database(
    tmp_path: Path,
) -> None:
    database = tmp_path / "permplaces.db"
    backup = tmp_path / "backup.db"
    _create_database(database, "old")
    _create_database(backup, "new")

    safety_backup = restore_database(
        backup,
        database,
        confirm_stopped=True,
    )

    assert safety_backup is not None
    assert safety_backup.is_file()
    assert _read_value(database) == "new"
    assert _read_value(safety_backup) == "old"
    assert verify_database(database) == database



def test_inspect_database_reports_schema_and_counts_without_rows(tmp_path: Path) -> None:
    database = tmp_path / "permplaces.db"
    with sqlite3.connect(database) as connection:
        connection.execute("PRAGMA user_version = 2")
        connection.execute(
            """
            CREATE TABLE favorites (
                user_id INTEGER NOT NULL,
                venue_id TEXT NOT NULL,
                payload TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (user_id, venue_id)
            )
            """
        )
        connection.execute(
            "INSERT INTO favorites (user_id, venue_id, payload) VALUES (42, 'osm:1', '{}')"
        )
        connection.execute(
            """
            CREATE TABLE venue_ratings (
                user_id INTEGER NOT NULL,
                venue_key TEXT NOT NULL,
                score INTEGER NOT NULL,
                updated_at_ns INTEGER NOT NULL,
                PRIMARY KEY (user_id, venue_key)
            )
            """
        )
        connection.executemany(
            """
            INSERT INTO venue_ratings (user_id, venue_key, score, updated_at_ns)
            VALUES (?, ?, ?, ?)
            """,
            [
                (42, "osm:node/1", 5, 1),
                (43, "osm:node/1", 4, 2),
            ],
        )
        connection.execute(
            """
            CREATE TABLE provider_daily_request_budget (
                provider TEXT NOT NULL,
                day TEXT NOT NULL,
                used INTEGER NOT NULL,
                PRIMARY KEY (provider, day)
            )
            """
        )
        connection.execute(
            """
            INSERT INTO provider_daily_request_budget (provider, day, used)
            VALUES ('geoapify', '2026-10-01', 12)
            """
        )
        connection.execute(
            """
            CREATE TABLE favorite_identity_aliases (
                user_id INTEGER NOT NULL,
                venue_id TEXT NOT NULL,
                identity_key TEXT NOT NULL,
                PRIMARY KEY (user_id, venue_id, identity_key)
            )
            """
        )
        connection.executemany(
            """
            INSERT INTO favorite_identity_aliases (
                user_id,
                venue_id,
                identity_key
            )
            VALUES (?, ?, ?)
            """,
            [
                (42, "osm:1", "osm:1"),
                (42, "osm:1", "geoapify:place-1"),
            ],
        )
        connection.commit()

    inspection = inspect_database(database)

    assert inspection.schema_version == 2
    assert inspection.favorites == 1
    assert inspection.favorite_aliases == 2
    assert inspection.ratings == 2
    assert inspection.provider_budget_rows == 1


def test_inspect_database_tolerates_legacy_missing_app_tables(tmp_path: Path) -> None:
    database = tmp_path / "legacy.db"
    _create_database(database, "legacy")

    inspection = inspect_database(database)

    assert inspection.schema_version == 0
    assert inspection.favorites is None
    assert inspection.favorite_aliases is None
    assert inspection.ratings is None
    assert inspection.provider_budget_rows is None
