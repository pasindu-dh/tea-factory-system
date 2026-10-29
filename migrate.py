"""Ordered, dependency-free schema migrations driven by PRAGMA user_version.

`schema.sql` is the frozen *version 0* baseline: it creates a brand-new database
and nothing more. Every subsequent schema change lives in `migrations/` as a
numbered .sql file, so databases created before that change actually receive it
— editing schema.sql would only ever affect freshly created databases.

    migrations/001_salaries_payment_details.sql

Migrations run in filename order, each inside its own transaction, and the
applied version is recorded in the database header. SQLite has transactional
DDL, so a migration that fails part-way leaves the version untouched and the
file safe to retry.

The statements are executed one by one rather than through
`Connection.executescript()`: executescript() implicitly commits any open
transaction before it runs, which would defeat the rollback guarantee above.

Migration is an explicit operator action (`flask migrate`); the web process
never runs DDL on its own, because two workers starting together would race.
"""
from __future__ import annotations

import re
import sqlite3
from pathlib import Path

MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"

# 001_salaries_payment_details.sql -> version 1
_NAME_RE = re.compile(r"^(\d{3})_[a-z0-9_]+\.sql$")

# schema.sql itself is version 0; migrations start at 1.
BASELINE_VERSION = 0


class MigrationError(RuntimeError):
    """Raised when the migration set and the database cannot be reconciled."""


def discover(migrations_dir: Path | None = None) -> list[tuple[int, Path]]:
    """Return [(version, path)] sorted by version, validating the filenames."""
    directory = migrations_dir or MIGRATIONS_DIR
    if not directory.exists():
        return []

    found: list[tuple[int, Path]] = []
    seen: dict[int, str] = {}
    for path in sorted(directory.glob("*.sql")):
        match = _NAME_RE.match(path.name)
        if not match:
            raise MigrationError(
                f"Bad migration filename '{path.name}' — expected NNN_lower_snake_case.sql"
            )
        version = int(match.group(1))
        if version == BASELINE_VERSION:
            raise MigrationError(
                f"'{path.name}' is version {BASELINE_VERSION}, which is reserved for schema.sql"
            )
        if version in seen:
            raise MigrationError(
                f"Duplicate migration version {version}: '{seen[version]}' and '{path.name}'"
            )
        seen[version] = path.name
        found.append((version, path))

    return sorted(found)


def latest_version(migrations_dir: Path | None = None) -> int:
    """The highest migration version available on disk (0 if there are none)."""
    known = discover(migrations_dir)
    return known[-1][0] if known else BASELINE_VERSION


def current_version(conn: sqlite3.Connection) -> int:
    return int(conn.execute("PRAGMA user_version").fetchone()[0])


def pending_from(conn: sqlite3.Connection, migrations_dir: Path | None = None) -> list[int]:
    """Migration versions not yet applied to this connection's database."""
    applied = current_version(conn)
    return [version for version, _ in discover(migrations_dir) if version > applied]


def _iter_statements(sql: str):
    """Yield complete SQL statements from a migration file.

    `sqlite3.complete_statement` understands quoted semicolons and comments, so
    statements are split on real terminators rather than every `;`.
    """
    buffer = ""
    for line in sql.splitlines(keepends=True):
        buffer += line
        if sqlite3.complete_statement(buffer):
            statement = buffer.strip()
            if statement:
                yield statement
            buffer = ""

    tail = buffer.strip()
    if tail and any(
        line.strip() and not line.strip().startswith("--") for line in tail.splitlines()
    ):
        yield tail


def apply_migrations(db_path, *, echo=print, migrations_dir: Path | None = None) -> list[int]:
    """Apply every pending migration to `db_path`; return the versions applied."""
    known = discover(migrations_dir)
    if not known:
        return []

    conn = sqlite3.connect(str(db_path))
    try:
        applied = current_version(conn)
        highest_known = known[-1][0]

        if applied > highest_known:
            raise MigrationError(
                f"Database is at schema version {applied}, but this code only knows "
                f"up to version {highest_known}. Refusing to run against a newer "
                f"database — upgrade the application code instead."
            )

        done: list[int] = []
        for version, path in known:
            if version <= applied:
                continue

            sql = path.read_text(encoding="utf-8")
            conn.execute("BEGIN IMMEDIATE")
            try:
                for statement in _iter_statements(sql):
                    conn.execute(statement)
                # PRAGMA statements cannot be parameterised ('PRAGMA user_version = ?'
                # is a syntax error), so the value is interpolated. `version` comes
                # from _NAME_RE's 3-digit capture group, so it is always an int.
                conn.execute(f"PRAGMA user_version = {int(version)}")
                conn.commit()
            except Exception:
                conn.rollback()
                raise
            done.append(version)
            echo(f"Applied {path.name} (version {version})")

        return done
    finally:
        conn.close()
