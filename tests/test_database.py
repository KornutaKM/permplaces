import json
import sqlite3

import pytest

from app.database import SCHEMA_VERSION, DatabaseSchemaError, initialize_database


@pytest.mark.asyncio
async def test_initialize_database_creates_current_schema(tmp_path) -> None:
    path = tmp_path / "permplaces.db"

    await initialize_database(str(path))

    with sqlite3.connect(path) as database:
        version = database.execute("PRAGMA user_version").fetchone()[0]
        tables = {
            row[0]
            for row in database.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        indexes = {
            row[0]
            for row in database.execute(
                "SELECT name FROM sqlite_master WHERE type = 'index'"
            )
        }

    assert version == SCHEMA_VERSION
    assert {
        "favorites",
        "favorite_identity_aliases",
        "venue_ratings",
        "provider_daily_request_budget",
    } <= tables
    assert "idx_venue_ratings_venue_key" in indexes
    assert "idx_favorite_identity_aliases_lookup" in indexes


@pytest.mark.asyncio
async def test_initialize_database_migrates_legacy_tables_without_data_loss(
    tmp_path,
) -> None:
    path = tmp_path / "permplaces.db"
    with sqlite3.connect(path) as database:
        database.execute(
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
        database.execute(
            "INSERT INTO favorites (user_id, venue_id, payload) VALUES (1, 'osm:1', '{}')"
        )
        database.execute(
            """
            CREATE TABLE venue_ratings (
                user_id INTEGER NOT NULL,
                venue_key TEXT NOT NULL,
                score INTEGER NOT NULL CHECK (score BETWEEN 1 AND 5),
                updated_at_ns INTEGER NOT NULL,
                PRIMARY KEY (user_id, venue_key)
            )
            """
        )
        database.execute(
            """
            INSERT INTO venue_ratings (user_id, venue_key, score, updated_at_ns)
            VALUES (1, 'osm:node/1', 5, 123)
            """
        )
        database.commit()

    await initialize_database(str(path))

    with sqlite3.connect(path) as database:
        assert database.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION
        assert database.execute("SELECT COUNT(*) FROM favorites").fetchone()[0] == 1
        assert database.execute("SELECT COUNT(*) FROM venue_ratings").fetchone()[0] == 1
        assert (
            database.execute(
                "SELECT COUNT(*) FROM provider_daily_request_budget"
            ).fetchone()[0]
            == 0
        )
        assert (
            database.execute(
                "SELECT identity_key FROM favorite_identity_aliases"
            ).fetchall()
            == [("osm:1",)]
        )


@pytest.mark.asyncio
async def test_initialize_database_rejects_future_schema(tmp_path) -> None:
    path = tmp_path / "permplaces.db"
    with sqlite3.connect(path) as database:
        database.execute(f"PRAGMA user_version = {SCHEMA_VERSION + 1}")

    with pytest.raises(DatabaseSchemaError, match="newer than this application"):
        await initialize_database(str(path))


@pytest.mark.asyncio
async def test_initialize_database_is_idempotent(tmp_path) -> None:
    path = tmp_path / "permplaces.db"

    await initialize_database(str(path))
    await initialize_database(str(path))

    with sqlite3.connect(path) as database:
        assert database.execute("PRAGMA quick_check").fetchone()[0] == "ok"
        assert database.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION



@pytest.mark.asyncio
async def test_initialize_database_rejects_malformed_legacy_table(tmp_path) -> None:
    path = tmp_path / "permplaces.db"
    with sqlite3.connect(path) as database:
        database.execute(
            """
            CREATE TABLE favorites (
                user_id INTEGER NOT NULL,
                venue_id TEXT NOT NULL,
                PRIMARY KEY (user_id, venue_id)
            )
            """
        )
        database.commit()

    with pytest.raises(DatabaseSchemaError, match="missing required columns"):
        await initialize_database(str(path))

    with sqlite3.connect(path) as database:
        assert database.execute("PRAGMA user_version").fetchone()[0] == 0



@pytest.mark.asyncio
async def test_schema_v1_migration_backfills_all_favorite_provider_aliases(
    tmp_path,
) -> None:
    path = tmp_path / "permplaces.db"
    payload = json.dumps(
        {
            "id": "geoapify:place-9",
            "source": "geoapify",
            "source_id": "place-9",
            "source_refs": [
                {"provider": "geoapify", "source_id": "place-9"},
                {"provider": "osm", "source_id": "node/9"},
            ],
        }
    )

    with sqlite3.connect(path) as database:
        database.execute("PRAGMA user_version = 1")
        database.execute(
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
        database.execute(
            """
            CREATE TABLE venue_ratings (
                user_id INTEGER NOT NULL,
                venue_key TEXT NOT NULL,
                score INTEGER NOT NULL CHECK (score BETWEEN 1 AND 5),
                updated_at_ns INTEGER NOT NULL,
                PRIMARY KEY (user_id, venue_key)
            )
            """
        )
        database.execute(
            """
            CREATE TABLE provider_daily_request_budget (
                provider TEXT NOT NULL,
                day TEXT NOT NULL,
                used INTEGER NOT NULL CHECK (used >= 0),
                PRIMARY KEY (provider, day)
            )
            """
        )
        database.execute(
            """
            INSERT INTO favorites (user_id, venue_id, payload)
            VALUES (7, 'geoapify:place-9', ?)
            """,
            (payload,),
        )
        database.commit()

    await initialize_database(str(path))

    with sqlite3.connect(path) as database:
        aliases = database.execute(
            """
            SELECT identity_key
            FROM favorite_identity_aliases
            WHERE user_id = 7
            ORDER BY identity_key
            """
        ).fetchall()
        version = database.execute("PRAGMA user_version").fetchone()[0]

    assert version == SCHEMA_VERSION
    assert aliases == [
        ("geoapify:place-9",),
        ("osm:node/9",),
    ]


@pytest.mark.asyncio
async def test_schema_v2_migration_falls_back_to_venue_id_for_bad_payload(
    tmp_path,
) -> None:
    path = tmp_path / "permplaces.db"
    with sqlite3.connect(path) as database:
        database.execute("PRAGMA user_version = 1")
        database.execute(
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
        database.execute(
            """
            CREATE TABLE venue_ratings (
                user_id INTEGER NOT NULL,
                venue_key TEXT NOT NULL,
                score INTEGER NOT NULL CHECK (score BETWEEN 1 AND 5),
                updated_at_ns INTEGER NOT NULL,
                PRIMARY KEY (user_id, venue_key)
            )
            """
        )
        database.execute(
            """
            CREATE TABLE provider_daily_request_budget (
                provider TEXT NOT NULL,
                day TEXT NOT NULL,
                used INTEGER NOT NULL CHECK (used >= 0),
                PRIMARY KEY (provider, day)
            )
            """
        )
        database.execute(
            """
            INSERT INTO favorites (user_id, venue_id, payload)
            VALUES (8, 'osm:node/bad', 'not-json')
            """
        )
        database.commit()

    await initialize_database(str(path))

    with sqlite3.connect(path) as database:
        aliases = database.execute(
            """
            SELECT identity_key
            FROM favorite_identity_aliases
            WHERE user_id = 8
            """
        ).fetchall()

    assert aliases == [("osm:node/bad",)]
