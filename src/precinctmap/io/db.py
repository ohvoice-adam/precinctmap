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
    if key != ":memory:":
        Path(key).parent.mkdir(parents=True, exist_ok=True)
    try:
        con = duckdb.connect(key)
    except duckdb.IOException as exc:
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
    _CONNECTIONS[key] = con
    return con


def close_all() -> None:
    """Close every shared connection (tests, CLI shutdown)."""
    for con in _CONNECTIONS.values():
        con.close()
    _CONNECTIONS.clear()
