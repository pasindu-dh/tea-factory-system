"""The migration runner: ordering, idempotence, downgrade refusal, and a real upgrade.

The last test is the one that matters: it builds a database using *only*
schema.sql (the version 0 baseline, exactly as an existing installation would
have it), then proves a migration actually delivers a new column to it.
"""
from __future__ import annotations

import sqlite3

import pytest

import db as db_module
import migrate
from db import query_one


def _columns(conn, table: str) -> set[str]:
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}


def _schema_only_db(path) -> sqlite3.Connection:
    """A database exactly as a pre-migration installation would be: version 0."""
    conn = sqlite3.connect(str(path))
    conn.executescript(db_module.SCHEMA_FILE.read_text(encoding="utf-8"))
    conn.commit()
    return conn


def test_migrations_are_discovered_in_order():
    versions = [version for version, _ in migrate.discover()]
    assert versions == sorted(versions)
    assert versions, "expected at least one migration"
    assert versions[0] == 1


def test_fresh_database_reaches_the_latest_version(app):
    with app.app_context():
        assert query_one("PRAGMA user_version")[0] == migrate.latest_version()

    conn = sqlite3.connect(app.config["DATABASE"])
    try:
        assert migrate.pending_from(conn) == []
    finally:
        conn.close()


def test_init_db_is_idempotent(app):
    """Running init_db again must not re-apply migrations or raise."""
    db_module.init_db(app)
    with app.app_context():
        assert query_one("PRAGMA user_version")[0] == migrate.latest_version()


def test_upgrade_path_from_the_version_zero_baseline(tmp_path):
    path = tmp_path / "legacy.sqlite3"
    conn = _schema_only_db(path)
    try:
        assert migrate.current_version(conn) == 0
        assert "payment_method" not in _columns(conn, "salaries")
    finally:
        conn.close()

    applied = migrate.apply_migrations(path, echo=lambda _message: None)
    assert applied == [1, 2]

    conn = sqlite3.connect(str(path))
    try:
        assert migrate.current_version(conn) == 2
        assert "payment_method" in _columns(conn, "salaries")
        assert "payment_ref" in _columns(conn, "salaries")
        tables = {
            row[0]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        assert "supervisor_sections" in tables
    finally:
        conn.close()


def test_supervisor_sections_migration_copies_existing_area(tmp_path):
    """A version-1 database keeps every supervisor's single section."""
    path = tmp_path / "legacy-supervisor.sqlite3"
    conn = _schema_only_db(path)
    try:
        conn.execute("PRAGMA user_version = 1")
        conn.execute(
            """INSERT INTO users
                   (name, role, gender, phone, password_hash, work_type, area)
               VALUES ('Legacy Sup', 'supervisor', 'Male', '0770000901',
                       'x', NULL, 'Factory Processing')"""
        )
        conn.execute(
            """INSERT INTO users
                   (name, role, gender, phone, password_hash, work_type, area)
               VALUES ('No Section', 'supervisor', 'Male', '0770000902',
                       'x', NULL, NULL)"""
        )
        conn.commit()
        supervisor_id = conn.execute(
            "SELECT user_id FROM users WHERE phone = '0770000901'"
        ).fetchone()[0]
    finally:
        conn.close()

    assert migrate.apply_migrations(path, echo=lambda _m: None) == [2]

    conn = sqlite3.connect(str(path))
    try:
        rows = conn.execute(
            "SELECT supervisor_id, area FROM supervisor_sections"
        ).fetchall()
        assert rows == [(supervisor_id, "Factory Processing")]
    finally:
        conn.close()


def test_apply_migrations_is_idempotent(tmp_path):
    path = tmp_path / "twice.sqlite3"
    _schema_only_db(path).close()

    assert migrate.apply_migrations(path, echo=lambda _m: None) == [1, 2]
    # Second run has nothing to do, and must not raise or bump the version again.
    assert migrate.apply_migrations(path, echo=lambda _m: None) == []

    conn = sqlite3.connect(str(path))
    try:
        assert migrate.current_version(conn) == 2
    finally:
        conn.close()


def test_database_newer_than_the_code_is_refused(tmp_path):
    path = tmp_path / "future.sqlite3"
    conn = _schema_only_db(path)
    conn.execute("PRAGMA user_version = 999")
    conn.commit()
    conn.close()

    with pytest.raises(migrate.MigrationError, match="999"):
        migrate.apply_migrations(path, echo=lambda _m: None)


def test_bad_migration_filenames_are_rejected(tmp_path):
    (tmp_path / "add_something.sql").write_text("SELECT 1;", encoding="utf-8")
    with pytest.raises(migrate.MigrationError, match="Bad migration filename"):
        migrate.discover(tmp_path)

    (tmp_path / "add_something.sql").unlink()
    (tmp_path / "000_baseline.sql").write_text("SELECT 1;", encoding="utf-8")
    with pytest.raises(migrate.MigrationError, match="reserved"):
        migrate.discover(tmp_path)


def test_duplicate_versions_are_rejected(tmp_path):
    (tmp_path / "002_a.sql").write_text("SELECT 1;", encoding="utf-8")
    (tmp_path / "002_b.sql").write_text("SELECT 1;", encoding="utf-8")
    with pytest.raises(migrate.MigrationError, match="Duplicate migration version 2"):
        migrate.discover(tmp_path)


def test_failed_migration_rolls_back_completely(tmp_path):
    migrations = tmp_path / "migrations"
    migrations.mkdir()
    (migrations / "001_broken.sql").write_text(
        "CREATE TABLE should_not_survive (id INTEGER);\n"
        "INSERT INTO table_that_does_not_exist VALUES (1);\n",
        encoding="utf-8",
    )
    path = tmp_path / "broken.sqlite3"
    _schema_only_db(path).close()

    with pytest.raises(sqlite3.OperationalError):
        migrate.apply_migrations(
            path, echo=lambda _message: None, migrations_dir=migrations
        )

    conn = sqlite3.connect(str(path))
    try:
        assert migrate.current_version(conn) == 0
        tables = {
            row[0]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        assert "should_not_survive" not in tables
    finally:
        conn.close()
