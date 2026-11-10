"""SQLite access for the compatibility registry.

Design notes (per spec):
- Not a service: opened inside rag-shim only, thread-local connections.
- foreign_keys=ON on every connection, bounded busy_timeout, WAL journal.
- Schema is applied from compat/schema.sql (CREATE ... IF NOT EXISTS) => idempotent.
"""
import os
import sqlite3
import threading

_SCHEMA_FILE = os.path.join(os.path.dirname(__file__), "schema.sql")
_local = threading.local()


def db_path() -> str:
    """Config comes from the environment (rag.env); no credentials here."""
    return os.environ.get("COMPAT_DB", os.path.expanduser("~/rag/shim/data/compatibility.db"))


def connect() -> sqlite3.Connection:
    path = db_path()
    conn = getattr(_local, "conn", None)
    if conn is not None and getattr(_local, "path", None) == path:
        return conn
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    conn = sqlite3.connect(path, timeout=5.0, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 3000")
    conn.execute("PRAGMA journal_mode = WAL")
    _local.conn = conn
    _local.path = path
    return conn


def schema_version(conn: sqlite3.Connection) -> str:
    row = conn.execute("SELECT value FROM schema_meta WHERE key='schema_version'").fetchone()
    return row["value"] if row else "0"


def init_db(conn: sqlite3.Connection) -> dict:
    """Apply the schema idempotently and report the resulting version."""
    ddl = open(_SCHEMA_FILE, encoding="utf-8").read()
    conn.executescript(ddl)
    conn.commit()
    tables = [r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
    return {"db_path": db_path(), "schema_version": schema_version(conn), "tables": tables}
