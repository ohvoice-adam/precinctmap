"""Commit a reviewed staging batch into the catalog, atomically.

Re-committing a file already ingested (same sha256) is a no-op. A different file for an
election that already has one supersedes it: the old rows are removed, the old source_files
row is kept as 'superseded', and an ingest_events row records the replacement.
"""

import json
import shutil
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import duckdb

from precinctmap.config import Settings
from precinctmap.ingest.errors import StagingError
from precinctmap.ingest.staging import sha256_file, staging_dir

DATA_TABLES = (
    "contests",
    "choices",
    "precinct_results",
    "precinct_sources",
    "precinct_turnout",
    "out_of_county_results",
)
LOG_TABLES = ("normalization_log", "unmatched_precincts")


@dataclass(frozen=True)
class CommitResult:
    action: str  # 'commit' | 'noop'
    election_id: str
    file_id: str
    detail: str


def _load_manifest(settings: Settings, staging_id: str) -> tuple[Path, dict[str, Any]]:
    directory = staging_dir(settings, staging_id)
    path = directory / "manifest.json"
    if not path.exists():
        raise StagingError(f"no staging batch {staging_id} (looked for {path})")
    manifest: dict[str, Any] = json.loads(path.read_text())
    return directory, manifest


def commit_staging(
    con: duckdb.DuckDBPyConnection, settings: Settings, staging_id: str, allow_replace: bool = False
) -> CommitResult:
    """Commit a ready batch. Replacing an election's loaded file needs `allow_replace`."""
    directory, m = _load_manifest(settings, staging_id)
    election = m["election"]
    if m["status"] == "committed":
        loaded = con.execute(
            "SELECT 1 FROM source_files WHERE file_id = ?", [m["sha256"]]
        ).fetchone()
        if loaded:
            return CommitResult("noop", election["election_id"], m["sha256"], "already committed")
        raise StagingError(
            f"{staging_id} is marked committed, but this store doesn't have {m['filename']}"
            " (the staging folder was probably copied from another machine, or the store was"
            " reset). Re-stage the file with `precinctmap ingest <file> --review`, then commit."
        )
    if m["status"] != "ready":
        raise StagingError(f"{staging_id} is {m['status']}; see {directory / 'report.txt'}")
    source = directory / m["source_copy"]
    if sha256_file(source) != m["sha256"]:
        raise StagingError(f"{staging_id}: staged source no longer matches its sha256")
    exists = con.execute("SELECT 1 FROM source_files WHERE sha256 = ?", [m["sha256"]]).fetchone()
    if exists and not m.get("reprocess"):
        _event(
            con, staging_id, "noop", election["election_id"], m["sha256"], "sha256 already ingested"
        )
        return CommitResult("noop", election["election_id"], m["sha256"], "sha256 already ingested")
    _check_replace(con, election["election_id"], m, allow_replace)
    raw = settings.data_dir / "raw" / f"{m['sha256'][:12]}__{m['filename']}"
    raw.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, raw)
    con.execute("BEGIN")
    try:
        if m.get("reprocess"):
            _remove_file(con, m["staging_id"], election["election_id"], m["sha256"])
        detail = _apply(con, directory, m, raw)
        con.execute("COMMIT")
    except Exception:
        con.execute("ROLLBACK")
        raise
    m["status"], m["committed_at"] = "committed", datetime.now(UTC).isoformat()
    (directory / "manifest.json").write_text(json.dumps(m, indent=2))
    return CommitResult("commit", election["election_id"], m["sha256"], detail)


def _check_replace(
    con: duckdb.DuckDBPyConnection, election_id: str, m: dict[str, Any], allow_replace: bool
) -> None:
    row = con.execute(
        "SELECT filename FROM source_files WHERE election_id = ? AND status = 'active'"
        " AND sha256 <> ?",
        [election_id, m["sha256"]],
    ).fetchone()
    if row is not None and not allow_replace:
        raise StagingError(
            f"{m['staging_id']} would replace {row[0]}, the loaded file for {election_id};"
            " confirm the replacement (--replace / replace=true) to commit"
        )


def _apply(con: duckdb.DuckDBPyConnection, directory: Path, m: dict[str, Any], raw: Path) -> str:
    e, file_id = m["election"], m["sha256"]
    superseded = _supersede(con, m["staging_id"], e["election_id"], file_id)
    con.execute(
        "INSERT INTO elections VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT (election_id)"
        " DO UPDATE SET label = excluded.label, certified = excluded.certified",
        [e["election_id"], e["county"], e["date"], e["type"], e["label"], e["certified"]],
    )
    for table in DATA_TABLES + LOG_TABLES:
        parquet = directory / f"{table}.parquet"
        if parquet.exists():
            con.execute(f"INSERT INTO {table} BY NAME SELECT * FROM read_parquet('{parquet}')")
    adapter, _, version = m["adapter"].partition(" v")
    con.execute(
        "INSERT INTO source_files (file_id, election_id, filename, sha256, stored_path, adapter,"
        " adapter_version, staging_id, ingested_at, row_count, status)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, current_timestamp, ?, 'active')",
        [
            file_id,
            e["election_id"],
            m["filename"],
            m["sha256"],
            str(raw),
            adapter,
            version,
            m["staging_id"],
            m["precinct_rows"],
        ],
    )
    _verify_counts(con, m)
    detail = f"{m['row_counts'].get('precinct_results', 0):,} result rows"
    if superseded:
        detail += f"; superseded {superseded}"
    _event(con, m["staging_id"], "commit", e["election_id"], file_id, detail)
    return detail


def _supersede(
    con: duckdb.DuckDBPyConnection, staging_id: str, election_id: str, new_id: str
) -> str | None:
    row = con.execute(
        "SELECT file_id, filename FROM source_files WHERE election_id = ? AND status = 'active'",
        [election_id],
    ).fetchone()
    if row is None:
        return None
    old_id, old_name = row
    for table in DATA_TABLES:
        con.execute(f"DELETE FROM {table} WHERE file_id = ?", [old_id])
    con.execute(
        "UPDATE source_files SET status = 'superseded', superseded_by = ? WHERE file_id = ?",
        [new_id, old_id],
    )
    _event(con, staging_id, "supersede", election_id, old_id, f"{old_name} replaced by {new_id}")
    return str(old_name)


def _remove_file(
    con: duckdb.DuckDBPyConnection, staging_id: str, election_id: str, file_id: str
) -> None:
    """Delete every row a file produced so it can be re-derived (reprocess)."""
    for table in DATA_TABLES + LOG_TABLES:
        con.execute(f"DELETE FROM {table} WHERE file_id = ?", [file_id])
    con.execute("DELETE FROM source_files WHERE file_id = ?", [file_id])
    _event(con, staging_id, "reprocess", election_id, file_id, "rows re-derived from same file")


def _verify_counts(con: duckdb.DuckDBPyConnection, m: dict[str, Any]) -> None:
    """Rows in == rows out for every staged table (rule 1)."""
    for table, expected in m["row_counts"].items():
        row = con.execute(
            f"SELECT count(*) FROM {table} WHERE file_id = ?", [m["sha256"]]
        ).fetchone()
        got = row[0] if row else 0
        if got != expected:
            raise StagingError(f"{table}: staged {expected} rows but {got} landed")


def _event(
    con: duckdb.DuckDBPyConnection,
    staging_id: str,
    action: str,
    election_id: str | None,
    file_id: str | None,
    detail: str,
) -> None:
    con.execute(
        "INSERT INTO ingest_events (staging_id, action, election_id, file_id, detail)"
        " VALUES (?, ?, ?, ?, ?)",
        [staging_id, action, election_id, file_id, detail],
    )
