import sqlite3
from pathlib import Path

import pytest

from app.db_admin import (
    DatabaseAdminError,
    backup_database,
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
