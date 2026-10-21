"""Ordered SQL migrations in `catalog/migrations/NNNN_name.sql`, applied once each.

An applied migration whose file later changes is an error: write a new migration instead.
"""

import hashlib
from importlib.resources import files

import duckdb

_BOOTSTRAP = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    version    INTEGER PRIMARY KEY,
    name       VARCHAR NOT NULL,
    sha256     VARCHAR NOT NULL,
    applied_at TIMESTAMP NOT NULL DEFAULT current_timestamp
)
"""


class MigrationError(RuntimeError):
    pass


def _migrations() -> list[tuple[int, str, str]]:
    folder = files("precinctmap.catalog") / "migrations"
    out = []
    for entry in folder.iterdir():
        if entry.name.endswith(".sql"):
            version = int(entry.name.split("_", 1)[0])
            out.append((version, entry.name, entry.read_text(encoding="utf-8")))
    return sorted(out)


def apply_migrations(con: duckdb.DuckDBPyConnection) -> list[str]:
    """Apply pending migrations in order, each in its own transaction. Returns names applied."""
    con.execute(_BOOTSTRAP)
    done = {
        v: sha for v, sha in con.execute("SELECT version, sha256 FROM schema_migrations").fetchall()
    }
    applied = []
    for version, name, sql in _migrations():
        sha = hashlib.sha256(sql.encode()).hexdigest()
        if version in done:
            if done[version] != sha:
                raise MigrationError(f"{name} changed after it was applied; add a new migration")
            continue
        con.execute("BEGIN")
        try:
            con.execute(sql)
            con.execute(
                "INSERT INTO schema_migrations (version, name, sha256) VALUES (?, ?, ?)",
                [version, name, sha],
            )
            con.execute("COMMIT")
        except Exception:
            con.execute("ROLLBACK")
            raise
        applied.append(name)
    return applied
