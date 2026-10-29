"""SQLite helpers that keep the database encrypted at rest with Windows DPAPI."""
import ctypes
import os
import sqlite3
import tempfile
import threading
from contextlib import contextmanager

import config

_DB_MAGIC = b"NEUROSIGN-DPAPI-v1\n"
_DB_LOCK = threading.RLock()
_CRYPTPROTECT_UI_FORBIDDEN = 0x1


class _DataBlob(ctypes.Structure):
    _fields_ = [
        ("cbData", ctypes.c_uint32),
        ("pbData", ctypes.POINTER(ctypes.c_ubyte)),
    ]


def _dpapi_transform(data, protect):
    if os.name != "nt":
        raise RuntimeError("Encrypted NeuroSign storage currently requires Windows DPAPI.")

    crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    input_buffer = ctypes.create_string_buffer(data)
    input_blob = _DataBlob(
        len(data),
        ctypes.cast(input_buffer, ctypes.POINTER(ctypes.c_ubyte)),
    )
    output_blob = _DataBlob()

    if protect:
        transform = crypt32.CryptProtectData
        transform.argtypes = [
            ctypes.POINTER(_DataBlob), ctypes.c_wchar_p, ctypes.POINTER(_DataBlob),
            ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint32, ctypes.POINTER(_DataBlob),
        ]
        transform.restype = ctypes.c_int
        result = transform(
            ctypes.byref(input_blob), "NeuroSign local database",
            None, None, None, _CRYPTPROTECT_UI_FORBIDDEN, ctypes.byref(output_blob),
        )
    else:
        description = ctypes.c_wchar_p()
        transform = crypt32.CryptUnprotectData
        transform.argtypes = [
            ctypes.POINTER(_DataBlob), ctypes.POINTER(ctypes.c_wchar_p),
            ctypes.POINTER(_DataBlob), ctypes.c_void_p, ctypes.c_void_p,
            ctypes.c_uint32, ctypes.POINTER(_DataBlob),
        ]
        transform.restype = ctypes.c_int
        result = transform(
            ctypes.byref(input_blob), ctypes.byref(description),
            None, None, None, _CRYPTPROTECT_UI_FORBIDDEN, ctypes.byref(output_blob),
        )

    if not result:
        error = ctypes.get_last_error()
        raise OSError(error, "Windows could not encrypt or decrypt the NeuroSign database.")

    try:
        return ctypes.string_at(output_blob.pbData, output_blob.cbData)
    finally:
        kernel32.LocalFree.argtypes = [ctypes.c_void_p]
        kernel32.LocalFree.restype = ctypes.c_void_p
        kernel32.LocalFree(output_blob.pbData)
        if not protect and description:
            kernel32.LocalFree(ctypes.cast(description, ctypes.c_void_p))


def _encrypt_database(serialized):
    return _DB_MAGIC + _dpapi_transform(serialized, protect=True)


def _decrypt_database(encrypted):
    if not encrypted.startswith(_DB_MAGIC):
        raise ValueError("The NeuroSign database file has an unknown encryption format.")
    try:
        return _dpapi_transform(encrypted[len(_DB_MAGIC):], protect=False)
    except OSError as exc:
        raise RuntimeError(
            "NeuroSign could not decrypt its database. Sign in to the same Windows account "
            "that encrypted it, and do not replace or restore the database from another device."
        ) from exc


def _write_encrypted(path, serialized):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_path = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "wb") as file:
            file.write(_encrypt_database(serialized))
            file.flush()
            os.fsync(file.fileno())
        os.replace(temp_path, path)
    except Exception:
        if os.path.exists(temp_path):
            os.remove(temp_path)
        raise


def _load_database(path):
    if not path.exists():
        return None

    with path.open("rb") as file:
        header = file.read(len(_DB_MAGIC))
    if header == _DB_MAGIC:
        return _decrypt_database(path.read_bytes())

    with path.open("rb") as file:
        sqlite_header = file.read(16)
    if sqlite_header != b"SQLite format 3\x00":
        raise ValueError(
            f"{path} is neither a NeuroSign-encrypted database nor a valid SQLite database. "
            "The file was left unchanged."
        )

    uri = f"file:{path.resolve().as_posix()}?mode=ro"
    source = sqlite3.connect(uri, uri=True, timeout=10)
    try:
        return source.serialize()
    finally:
        source.close()


def _connect(serialized=None):
    conn = sqlite3.connect(":memory:", timeout=10)
    try:
        if serialized is not None:
            conn.deserialize(serialized)
        conn.row_factory = _dict_factory
        conn.execute("PRAGMA foreign_keys = ON")
        return conn
    except Exception:
        conn.close()
        raise


def _dict_factory(cursor, row):
    return {col[0]: row[i] for i, col in enumerate(cursor.description)}


@contextmanager
def get_connection():
    """Yields an in-memory SQLite connection and atomically persists it encrypted."""
    with _DB_LOCK:
        conn = _connect(_load_database(config.DB_PATH))
        try:
            yield conn
            conn.commit()
            _write_encrypted(config.DB_PATH, conn.serialize())
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()


def _is_old_schema(serialized):
    """True if users predates the age or account_id columns."""
    if serialized is None:
        return False
    conn = _connect(serialized)
    try:
        cols = [row["name"] for row in conn.execute("PRAGMA table_info(users)").fetchall()]
        return bool(cols) and ("age" not in cols or "account_id" not in cols)
    finally:
        conn.close()


def _ensure_movement_columns(conn):
    columns = {
        row["name"] for row in conn.execute("PRAGMA table_info(movement_results)").fetchall()
    }
    if "guide_deviation" not in columns:
        conn.execute("ALTER TABLE movement_results ADD COLUMN guide_deviation REAL")


def _backup_path(path):
    candidate = path.with_name(path.stem + "_old_v1" + path.suffix)
    suffix = 2
    while candidate.exists():
        candidate = path.with_name(f"{path.stem}_old_v1_{suffix}{path.suffix}")
        suffix += 1
    return candidate


def init_db():
    """Initialize schema and encrypt/migrate existing SQLite data without losing records."""
    with _DB_LOCK:
        path = config.DB_PATH
        serialized = _load_database(path)
        old_schema = _is_old_schema(serialized)

        conn = _connect(None if old_schema else serialized)
        try:
            sql = (config.BACKEND_DIR / "schema.sql").read_text(encoding="utf-8")
            conn.executescript(sql)
            _ensure_movement_columns(conn)
            conn.commit()
            initialized = conn.serialize()
        finally:
            conn.close()

        if old_schema and serialized is not None:
            backup = _backup_path(path)
            _write_encrypted(backup, serialized)
            print(f"[db] Old database preserved as encrypted backup {backup.name}", flush=True)

        _write_encrypted(path, initialized)
        print(f"[db] Encrypted database ready at {path}", flush=True)
