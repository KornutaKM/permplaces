import asyncio
import json
import sqlite3
from pathlib import Path

import pytest

from app.database import initialize_database
from app.db_admin import (
    DatabaseAdminError,
    audit_database,
    main as db_admin_main,
    backup_database,
    inspect_database,
    preflight_database,
    repair_favorite_aliases,
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
        connection.execute("PRAGMA user_version = 4")
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
        connection.execute(
            """
            CREATE TABLE favorite_notes (
                user_id INTEGER NOT NULL,
                identity_key TEXT NOT NULL,
                note TEXT NOT NULL,
                updated_at_ns INTEGER NOT NULL,
                PRIMARY KEY (user_id, identity_key)
            )
            """
        )
        connection.execute(
            """
            INSERT INTO favorite_notes (
                user_id,
                identity_key,
                note,
                updated_at_ns
            )
            VALUES (42, 'osm:1', 'Проверка', 10)
            """
        )
        connection.execute(
            """
            CREATE TABLE favorite_tags (
                user_id INTEGER NOT NULL,
                identity_key TEXT NOT NULL,
                tag TEXT NOT NULL,
                updated_at_ns INTEGER NOT NULL,
                PRIMARY KEY (user_id, identity_key, tag)
            )
            """
        )
        connection.executemany(
            """
            INSERT INTO favorite_tags (
                user_id,
                identity_key,
                tag,
                updated_at_ns
            )
            VALUES (?, ?, ?, ?)
            """,
            [
                (42, "osm:1", "want", 11),
                (42, "osm:1", "work", 12),
            ],
        )
        connection.commit()

    inspection = inspect_database(database)

    assert inspection.schema_version == 4
    assert inspection.favorites == 1
    assert inspection.favorite_aliases == 2
    assert inspection.notes == 1
    assert inspection.tags == 2
    assert inspection.ratings == 2
    assert inspection.provider_budget_rows == 1


def test_inspect_database_tolerates_legacy_missing_app_tables(tmp_path: Path) -> None:
    database = tmp_path / "legacy.db"
    _create_database(database, "legacy")

    inspection = inspect_database(database)

    assert inspection.schema_version == 0
    assert inspection.favorites is None
    assert inspection.favorite_aliases is None
    assert inspection.notes is None
    assert inspection.tags is None
    assert inspection.ratings is None
    assert inspection.provider_budget_rows is None



def _create_auditable_database(path: Path) -> None:
    asyncio.run(initialize_database(str(path)))
    payload = json.dumps(
        {
            "id": "geoapify:place-audit",
            "source": "geoapify",
            "source_id": "place-audit",
            "source_refs": [
                {"provider": "geoapify", "source_id": "place-audit"},
                {"provider": "osm", "source_id": "node/audit"},
            ],
        }
    )
    with sqlite3.connect(path) as connection:
        connection.execute(
            """
            INSERT INTO favorites (user_id, venue_id, payload)
            VALUES (10, 'geoapify:place-audit', ?)
            """,
            (payload,),
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
                (10, "geoapify:place-audit", "geoapify:place-audit"),
                (10, "geoapify:place-audit", "osm:node/audit"),
            ],
        )
        connection.commit()


def test_audit_database_reports_consistent_alias_index(tmp_path: Path) -> None:
    database = tmp_path / "permplaces.db"
    _create_auditable_database(database)

    audit = audit_database(database)

    assert audit.consistent is True
    assert audit.favorites == 1
    assert audit.expected_aliases == 2
    assert audit.actual_aliases == 2
    assert audit.missing_aliases == 0
    assert audit.unexpected_aliases == 0
    assert audit.orphan_aliases == 0


def test_audit_database_detects_missing_unexpected_and_orphan_aliases(
    tmp_path: Path,
) -> None:
    database = tmp_path / "permplaces.db"
    _create_auditable_database(database)

    with sqlite3.connect(database) as connection:
        connection.execute("DELETE FROM favorite_identity_aliases")
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
                (10, "geoapify:place-audit", "geoapify:wrong"),
                (10, "missing-favorite", "osm:orphan"),
            ],
        )
        connection.commit()

    audit = audit_database(database)

    assert audit.consistent is False
    assert audit.missing_aliases == 2
    assert audit.unexpected_aliases == 2
    assert audit.orphan_aliases == 1


def test_repair_favorite_aliases_requires_stopped_confirmation(
    tmp_path: Path,
) -> None:
    database = tmp_path / "permplaces.db"
    _create_auditable_database(database)

    with pytest.raises(DatabaseAdminError, match="confirm-stopped"):
        repair_favorite_aliases(database, confirm_stopped=False)


def test_repair_favorite_aliases_rebuilds_index_and_keeps_backup(
    tmp_path: Path,
) -> None:
    database = tmp_path / "permplaces.db"
    _create_auditable_database(database)

    with sqlite3.connect(database) as connection:
        connection.execute("DELETE FROM favorite_identity_aliases")
        connection.execute(
            """
            INSERT INTO favorite_identity_aliases (
                user_id,
                venue_id,
                identity_key
            )
            VALUES (10, 'missing-favorite', 'osm:orphan')
            """
        )
        connection.execute(
            """
            INSERT INTO venue_ratings (
                user_id,
                venue_key,
                score,
                updated_at_ns
            )
            VALUES (10, 'osm:node/audit', 5, 123)
            """
        )
        connection.commit()

    safety_backup = repair_favorite_aliases(
        database,
        confirm_stopped=True,
    )

    assert safety_backup.is_file()
    assert audit_database(database).consistent is True

    with sqlite3.connect(database) as connection:
        aliases = connection.execute(
            """
            SELECT identity_key
            FROM favorite_identity_aliases
            WHERE user_id = 10
            ORDER BY identity_key
            """
        ).fetchall()
        favorites = connection.execute(
            "SELECT COUNT(*) FROM favorites"
        ).fetchone()
        ratings = connection.execute(
            "SELECT COUNT(*) FROM venue_ratings"
        ).fetchone()

    assert aliases == [
        ("geoapify:place-audit",),
        ("osm:node/audit",),
    ]
    assert favorites == (1,)
    assert ratings == (1,)

    backup_audit = audit_database(safety_backup)
    assert backup_audit.consistent is False
    assert backup_audit.orphan_aliases == 1



def test_audit_database_detects_orphan_and_invalid_user_metadata(
    tmp_path: Path,
) -> None:
    database = tmp_path / "permplaces.db"
    _create_auditable_database(database)

    with sqlite3.connect(database) as connection:
        connection.execute("PRAGMA ignore_check_constraints = ON")
        connection.executemany(
            """
            INSERT INTO favorite_notes (
                user_id,
                identity_key,
                note,
                updated_at_ns
            )
            VALUES (?, ?, ?, ?)
            """,
            [
                (10, "osm:node/audit", "", 1),
                (10, "osm:node/missing", "orphan note", 2),
            ],
        )
        connection.executemany(
            """
            INSERT INTO favorite_tags (
                user_id,
                identity_key,
                tag,
                updated_at_ns
            )
            VALUES (?, ?, ?, ?)
            """,
            [
                (10, "osm:node/audit", "custom", 3),
                (10, "osm:node/missing", "want", 4),
            ],
        )
        connection.commit()

    audit = audit_database(database)

    assert audit.aliases_consistent is True
    assert audit.metadata_consistent is False
    assert audit.consistent is False
    assert audit.orphan_notes == 1
    assert audit.invalid_notes == 1
    assert audit.orphan_tags == 1
    assert audit.invalid_tags == 1


def test_metadata_audit_uses_favorite_payload_identities_not_drifted_alias_index(
    tmp_path: Path,
) -> None:
    database = tmp_path / "permplaces.db"
    _create_auditable_database(database)

    with sqlite3.connect(database) as connection:
        connection.execute(
            """
            INSERT INTO favorite_identity_aliases (
                user_id,
                venue_id,
                identity_key
            )
            VALUES (10, 'geoapify:place-audit', 'osm:node/unexpected')
            """
        )
        connection.execute(
            """
            INSERT INTO favorite_notes (
                user_id,
                identity_key,
                note,
                updated_at_ns
            )
            VALUES (10, 'osm:node/unexpected', 'must stay orphaned', 5)
            """
        )
        connection.commit()

    audit = audit_database(database)

    assert audit.aliases_consistent is False
    assert audit.orphan_notes == 1
    assert audit.metadata_consistent is False


def test_alias_repair_does_not_delete_or_block_on_unrelated_metadata_drift(
    tmp_path: Path,
) -> None:
    database = tmp_path / "permplaces.db"
    _create_auditable_database(database)

    with sqlite3.connect(database) as connection:
        connection.execute("DELETE FROM favorite_identity_aliases")
        connection.execute(
            """
            INSERT INTO favorite_notes (
                user_id,
                identity_key,
                note,
                updated_at_ns
            )
            VALUES (10, 'osm:node/orphan', 'preserve for operator recovery', 6)
            """
        )
        connection.commit()

    safety_backup = repair_favorite_aliases(
        database,
        confirm_stopped=True,
    )
    audit = audit_database(database)

    assert safety_backup.is_file()
    assert audit.aliases_consistent is True
    assert audit.metadata_consistent is False
    assert audit.orphan_notes == 1

    with sqlite3.connect(database) as connection:
        note = connection.execute(
            """
            SELECT note
            FROM favorite_notes
            WHERE identity_key = 'osm:node/orphan'
            """
        ).fetchone()

    assert note == ("preserve for operator recovery",)



def test_metadata_audit_tolerates_legacy_database_without_metadata_tables(
    tmp_path: Path,
) -> None:
    database = tmp_path / "permplaces.db"
    _create_auditable_database(database)

    with sqlite3.connect(database) as connection:
        connection.execute("DROP TABLE favorite_notes")
        connection.execute("DROP TABLE favorite_tags")
        connection.commit()

    audit = audit_database(database)

    assert audit.aliases_consistent is True
    assert audit.metadata_consistent is True
    assert audit.consistent is True
    assert audit.orphan_notes is None
    assert audit.invalid_notes is None
    assert audit.orphan_tags is None
    assert audit.invalid_tags is None



def test_preflight_database_reports_current_database_ready(tmp_path: Path) -> None:
    database = tmp_path / "permplaces.db"
    asyncio.run(initialize_database(str(database)))

    preflight = preflight_database(database)

    assert preflight.ready is True
    assert preflight.status == "ok"
    assert preflight.expected_schema_version == 4
    assert preflight.inspection.schema_version == 4
    assert preflight.missing_tables == ()
    assert preflight.missing_columns == ()
    assert preflight.missing_indexes == ()
    assert preflight.audit is not None
    assert preflight.audit.consistent is True


def test_preflight_database_reports_migration_required_without_audit(
    tmp_path: Path,
) -> None:
    database = tmp_path / "permplaces.db"
    asyncio.run(initialize_database(str(database)))
    with sqlite3.connect(database) as connection:
        connection.execute("PRAGMA user_version = 3")
        connection.commit()

    preflight = preflight_database(database)

    assert preflight.ready is False
    assert preflight.status == "migration_required"
    assert preflight.inspection.schema_version == 3
    assert preflight.audit is None


def test_preflight_database_reports_newer_schema_without_audit(
    tmp_path: Path,
) -> None:
    database = tmp_path / "permplaces.db"
    asyncio.run(initialize_database(str(database)))
    with sqlite3.connect(database) as connection:
        connection.execute("PRAGMA user_version = 5")
        connection.commit()

    preflight = preflight_database(database)

    assert preflight.ready is False
    assert preflight.status == "schema_newer"
    assert preflight.inspection.schema_version == 5
    assert preflight.audit is None


def test_preflight_database_detects_missing_required_table(tmp_path: Path) -> None:
    database = tmp_path / "permplaces.db"
    asyncio.run(initialize_database(str(database)))
    with sqlite3.connect(database) as connection:
        connection.execute("DROP TABLE favorite_tags")
        connection.commit()

    preflight = preflight_database(database)

    assert preflight.status == "schema_drift"
    assert preflight.ready is False
    assert preflight.missing_tables == ("favorite_tags",)
    assert preflight.audit is None


def test_preflight_database_detects_missing_required_column(tmp_path: Path) -> None:
    database = tmp_path / "permplaces.db"
    asyncio.run(initialize_database(str(database)))
    with sqlite3.connect(database) as connection:
        connection.execute("DROP TABLE favorite_notes")
        connection.execute(
            """
            CREATE TABLE favorite_notes (
                user_id INTEGER NOT NULL,
                identity_key TEXT NOT NULL,
                updated_at_ns INTEGER NOT NULL,
                PRIMARY KEY (user_id, identity_key)
            )
            """
        )
        connection.commit()

    preflight = preflight_database(database)

    assert preflight.status == "schema_drift"
    assert "favorite_notes.note" in preflight.missing_columns
    assert preflight.audit is None


def test_preflight_database_detects_missing_required_index(tmp_path: Path) -> None:
    database = tmp_path / "permplaces.db"
    asyncio.run(initialize_database(str(database)))
    with sqlite3.connect(database) as connection:
        connection.execute("DROP INDEX idx_favorite_tags_identity_key")
        connection.commit()

    preflight = preflight_database(database)

    assert preflight.status == "schema_drift"
    assert preflight.missing_indexes == ("idx_favorite_tags_identity_key",)
    assert preflight.audit is not None
    assert preflight.audit.consistent is True


def test_preflight_database_reports_data_drift_after_schema_passes(
    tmp_path: Path,
) -> None:
    database = tmp_path / "permplaces.db"
    _create_auditable_database(database)
    with sqlite3.connect(database) as connection:
        connection.execute("DELETE FROM favorite_identity_aliases")
        connection.commit()

    preflight = preflight_database(database)

    assert preflight.missing_tables == ()
    assert preflight.missing_columns == ()
    assert preflight.missing_indexes == ()
    assert preflight.audit is not None
    assert preflight.audit.consistent is False
    assert preflight.audit.missing_aliases == 2
    assert preflight.status == "data_drift"
    assert preflight.ready is False


def test_preflight_database_is_read_only_for_user_rows(tmp_path: Path) -> None:
    database = tmp_path / "permplaces.db"
    _create_auditable_database(database)
    with sqlite3.connect(database) as connection:
        connection.execute(
            """
            INSERT INTO favorite_notes (
                user_id,
                identity_key,
                note,
                updated_at_ns
            )
            VALUES (10, 'osm:node/audit', 'keep me', 100)
            """
        )
        connection.commit()

    preflight = preflight_database(database)

    assert preflight.ready is True
    with sqlite3.connect(database) as connection:
        favorite_row = connection.execute(
            "SELECT venue_id, payload FROM favorites WHERE user_id = 10"
        ).fetchone()
        note_row = connection.execute(
            """
            SELECT identity_key, note, updated_at_ns
            FROM favorite_notes
            WHERE user_id = 10
            """
        ).fetchone()

    assert favorite_row is not None
    assert favorite_row[0] == "geoapify:place-audit"
    assert note_row == ("osm:node/audit", "keep me", 100)



def test_preflight_cli_prints_only_safe_release_summary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = tmp_path / "permplaces.db"
    asyncio.run(initialize_database(str(database)))
    monkeypatch.setattr(
        "sys.argv",
        [
            "app.db_admin",
            "preflight",
            "--database",
            str(database),
        ],
    )

    exit_code = db_admin_main()
    output = capsys.readouterr().out

    assert exit_code == 0
    assert output.startswith("preflight_ok ")
    assert "app_version=0.44.0" in output
    assert "expected_schema_version=4" in output
    assert "schema_version=4" in output
    assert "missing_tables=-" in output
    assert "missing_columns=-" in output
    assert "missing_indexes=-" in output
    assert "audit_consistent=True" in output
    assert "user_id" not in output
    assert "payload" not in output
    assert "note=" not in output


def test_preflight_cli_exits_three_for_schema_mismatch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = tmp_path / "permplaces.db"
    asyncio.run(initialize_database(str(database)))
    with sqlite3.connect(database) as connection:
        connection.execute("PRAGMA user_version = 3")
        connection.commit()
    monkeypatch.setattr(
        "sys.argv",
        [
            "app.db_admin",
            "preflight",
            "--database",
            str(database),
        ],
    )

    exit_code = db_admin_main()
    output = capsys.readouterr().out

    assert exit_code == 3
    assert output.startswith("preflight_migration_required ")
    assert "audit_consistent=None" in output
