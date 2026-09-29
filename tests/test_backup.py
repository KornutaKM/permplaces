import sqlite3

import pytest

from app.backup import BackupError, create_backup, main, restore_backup, verify_database


def _create_database(path, *, value: str) -> None:
    with sqlite3.connect(path) as database:
        database.execute("PRAGMA journal_mode=WAL")
        database.execute(
            "CREATE TABLE favorites (id INTEGER PRIMARY KEY, value TEXT NOT NULL)"
        )
        database.execute("INSERT INTO favorites (value) VALUES (?)", (value,))
        database.commit()


def _read_value(path) -> str:
    with sqlite3.connect(path) as database:
        row = database.execute("SELECT value FROM favorites").fetchone()
    assert row is not None
    return str(row[0])


def test_create_backup_produces_verified_snapshot(tmp_path) -> None:
    source = tmp_path / "source.db"
    backup = tmp_path / "backups" / "snapshot.db"
    _create_database(source, value="original")

    result = create_backup(source, backup)

    assert result == backup
    assert verify_database(backup) == backup
    assert _read_value(backup) == "original"


def test_create_backup_refuses_to_overwrite_without_force(tmp_path) -> None:
    source = tmp_path / "source.db"
    backup = tmp_path / "snapshot.db"
    _create_database(source, value="original")
    create_backup(source, backup)

    with pytest.raises(FileExistsError):
        create_backup(source, backup)

    create_backup(source, backup, overwrite=True)
    assert _read_value(backup) == "original"


def test_verify_rejects_corrupt_database(tmp_path) -> None:
    corrupt = tmp_path / "corrupt.db"
    corrupt.write_bytes(b"not a sqlite database")

    with pytest.raises(BackupError):
        verify_database(corrupt)


def test_restore_refuses_existing_target_without_force(tmp_path) -> None:
    source = tmp_path / "source.db"
    backup = tmp_path / "snapshot.db"
    target = tmp_path / "target.db"
    _create_database(source, value="source")
    _create_database(target, value="target")
    create_backup(source, backup)

    with pytest.raises(FileExistsError):
        restore_backup(backup, target)

    assert _read_value(target) == "target"


def test_restore_replaces_database_and_removes_stale_sidecars(tmp_path) -> None:
    source = tmp_path / "source.db"
    backup = tmp_path / "snapshot.db"
    target = tmp_path / "target.db"
    _create_database(source, value="restored")
    _create_database(target, value="old")
    create_backup(source, backup)

    wal = tmp_path / "target.db-wal"
    shm = tmp_path / "target.db-shm"
    wal.write_bytes(b"stale wal")
    shm.write_bytes(b"stale shm")

    result = restore_backup(backup, target, overwrite=True)

    assert result == target
    assert _read_value(target) == "restored"
    assert not wal.exists()
    assert not shm.exists()
    assert verify_database(target) == target


def test_cli_returns_nonzero_for_missing_input(tmp_path, capsys) -> None:
    result = main(["verify", "--input", str(tmp_path / "missing.db")])

    assert result == 1
    assert "backup_error=" in capsys.readouterr().err


def test_cli_create_verify_restore_round_trip(tmp_path) -> None:
    source = tmp_path / "source.db"
    backup = tmp_path / "snapshot.db"
    restored = tmp_path / "restored.db"
    _create_database(source, value="round-trip")

    assert main(
        [
            "create",
            "--database",
            str(source),
            "--output",
            str(backup),
        ]
    ) == 0
    assert main(["verify", "--input", str(backup)]) == 0
    assert main(
        [
            "restore",
            "--input",
            str(backup),
            "--database",
            str(restored),
        ]
    ) == 0
    assert _read_value(restored) == "round-trip"
