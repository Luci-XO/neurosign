"""db.py - thin sqlite3 helpers (plain SQL, dict rows)."""
import sqlite3
from contextlib import contextmanager

import config


def _dict_factory(cursor, row):
    return {col[0]: row[i] for i, col in enumerate(cursor.description)}


@contextmanager
def get_connection():
    """Yields a connection; commits on success, rolls back on error."""
    conn = sqlite3.connect(str(config.DB_PATH), timeout=10)
    conn.row_factory = _dict_factory
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _is_old_schema(path):
    conn = sqlite3.connect(str(path))
    try:
        cols = [r[1] for r in conn.execute("PRAGMA table_info(users)").fetchall()]
    finally:
        conn.close()
    return bool(cols) and "age" not in cols


def init_db():
    """Create tables if missing. An older v1 database is renamed (not deleted) and replaced."""
    path = config.DB_PATH
    if path.exists() and _is_old_schema(path):
        backup = path.with_name(path.stem + "_old_v1" + path.suffix)
        if backup.exists():
            backup.unlink()
        path.rename(backup)
        print(f"[db] Old database moved to {backup.name}", flush=True)

    sql = (config.BACKEND_DIR / "schema.sql").read_text(encoding="utf-8")
    conn = sqlite3.connect(str(path))
    try:
        conn.executescript(sql)
        conn.commit()
    finally:
        conn.close()
    print(f"[db] Database ready at {path}", flush=True)