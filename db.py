"""SQLite access helpers: one connection per request, WAL mode, FK enforcement."""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path

from flask import current_app, g

import migrate

SCHEMA_FILE = Path(__file__).resolve().parent / "schema.sql"


def get_db() -> sqlite3.Connection:
    """Return the request-scoped connection, opening it on first use."""
    if "db" not in g:
        conn = sqlite3.connect(
            current_app.config["DATABASE"],
            detect_types=sqlite3.PARSE_DECLTYPES,
            timeout=5.0,
        )
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA busy_timeout = 5000")
        g.db = conn
    return g.db


def close_db(_exc=None) -> None:
    conn = g.pop("db", None)
    if conn is not None:
        conn.close()


def query_all(sql: str, params=()) -> list[sqlite3.Row]:
    return get_db().execute(sql, params).fetchall()


def query_one(sql: str, params=()) -> sqlite3.Row | None:
    return get_db().execute(sql, params).fetchone()


def _txn_depth() -> int:
    return getattr(g, "_txn_depth", 0)


@contextmanager
def transaction():
    """Group several writes into one atomic unit.

    Nested calls join the outermost transaction. While a transaction is open,
    `execute()` and `execute_many()` do not commit; the context manager commits
    once at the end, or rolls everything back if anything raises.
    """
    depth = _txn_depth()
    if depth:
        g._txn_depth = depth + 1
        try:
            yield get_db()
        finally:
            g._txn_depth = depth
        return

    conn = get_db()
    conn.execute("BEGIN IMMEDIATE")
    g._txn_depth = 1
    try:
        yield conn
        conn.commit()
    except BaseException:
        conn.rollback()
        raise
    finally:
        g._txn_depth = 0


def execute(sql: str, params=()) -> sqlite3.Cursor:
    conn = get_db()
    cur = conn.execute(sql, params)
    if not _txn_depth():
        conn.commit()
    return cur


def execute_many(sql: str, seq) -> sqlite3.Cursor:
    conn = get_db()
    cur = conn.executemany(sql, seq)
    if not _txn_depth():
        conn.commit()
    return cur


def init_db(app) -> None:
    """Create the database file (if needed), apply the schema, then migrate it."""
    db_path = Path(app.config["DATABASE"])
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(SCHEMA_FILE.read_text(encoding="utf-8"))
        conn.execute("PRAGMA journal_mode = WAL")
        conn.commit()
    finally:
        conn.close()

    # Runs on its own connection, after the one above is closed: journal_mode is
    # a no-op inside a transaction, and the migration runner manages its own.
    migrate.apply_migrations(db_path, echo=lambda _message: None)


def init_app(app) -> None:
    app.teardown_appcontext(close_db)
