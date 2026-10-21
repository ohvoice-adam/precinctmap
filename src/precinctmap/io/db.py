"""The single shared DuckDB connection (shared-instance pattern; no ad hoc connections).

Every module gets its connection from `get_connection`, which loads `spatial` and applies
pending migrations once per database path.
"""

import logging
import os
from pathlib import Path

import duckdb

from precinctmap.catalog.migrate import apply_migrations

log = logging.getLogger(__name__)

_CONNECTIONS: dict[str, duckdb.DuckDBPyConnection] = {}


class StoreLockedError(RuntimeError):
    """Another process (usually the running API) holds the store's write lock."""


class StoreUnavailableError(RuntimeError):
    """The store can't be opened or created (usually: its folder isn't writable)."""


def _unwritable(path: str, exc: Exception) -> StoreUnavailableError:
    folder = Path(path).parent.resolve()
    uid = os.getuid() if hasattr(os, "getuid") else "?"
    return StoreUnavailableError(
        f"cannot open the data store {path}: {exc}. The folder {folder} must exist and be"
        f" writable by the user the app runs as (uid {uid}). With Docker, create ./data"
        " yourself before the first start (a fresh clone includes it), or set"
        " PRECINCTMAP_UID / PRECINCTMAP_GID in .env to the folder's owner (`id -u`, `id -g`)."
    )


def _load_spatial(con: duckdb.DuckDBPyConnection) -> None:
    ext_dir = os.environ.get("PRECINCTMAP_DUCKDB_EXT_DIR")
    if ext_dir:
        quoted = ext_dir.replace("'", "''")
        con.execute(f"SET extension_directory = '{quoted}'")
    try:
        con.load_extension("spatial")
    except duckdb.Error:
        log.info("installing DuckDB spatial extension")
        con.install_extension("spatial")
        con.load_extension("spatial")


def get_connection(db_path: Path | str) -> duckdb.DuckDBPyConnection:
    """Open (or reuse) the store at `db_path`, with spatial loaded and the schema migrated.

    Pass ':memory:' for a throwaway database (tests).
    """
    key = str(db_path)
    con = _CONNECTIONS.get(key)
    if con is not None:
        return con
    try:
        if key != ":memory:":
            Path(key).parent.mkdir(parents=True, exist_ok=True)
        con = duckdb.connect(key)
    except PermissionError as exc:
        raise _unwritable(key, exc) from exc
    except duckdb.IOException as exc:
        if "permission denied" in str(exc).lower():
            raise _unwritable(key, exc) from exc
        if "lock" not in str(exc).lower():
            raise
        raise StoreLockedError(
            f"{key} is open in another process (is the API running?). Stop it, or use the"
            " admin upload page, which runs the same review and commit flow."
        ) from exc
    _load_spatial(con)
    applied = apply_migrations(con)
    if applied:
        log.info("applied migrations %s to %s", applied, key)
        # Write the new schema to the database file now. DuckDB 1.5 can fail to replay these
        # migrations from its write-ahead log ("Failure while replaying WAL file ... no default
        # database set"), so a process killed right after its first start left an unopenable
        # store.
        con.execute("CHECKPOINT")
    _CONNECTIONS[key] = con
    return con


def close_all() -> None:
    """Close every shared connection (tests, CLI shutdown)."""
    for con in _CONNECTIONS.values():
        con.close()
    _CONNECTIONS.clear()
