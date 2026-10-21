"""Staged ingest for parcels (review -> commit) and the voter-address reference table."""

import json
import shutil
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd

from precinctmap.config import Settings
from precinctmap.ingest.errors import StagingError
from precinctmap.ingest.staging import sha256_file
from precinctmap.parcels.assign import assign_parcels
from precinctmap.parcels.auditor import ADAPTER, read_parcels
from precinctmap.parcels.geos import assign_other
from precinctmap.parcels.report import build_report, render
from precinctmap.parcels.stats import materialize_stats
from precinctmap.parcels.units import estimate_apartment_units
from precinctmap.parcels.voterfile import read_voter_addresses

TABLES = ("parcels", "parcel_assignments", "parcel_log")


@dataclass(frozen=True)
class AddressLoad:
    action: str  # 'reviewed' | 'loaded' | 'noop'
    file_id: str
    rows_read: int
    addresses: int
    split_addresses: int
    columbus_addresses: int


def active_address_file(con: duckdb.DuckDBPyConnection) -> tuple[str, date] | None:
    row = con.execute("SELECT file_id, as_of FROM address_files WHERE status = 'active'").fetchone()
    return None if row is None else (str(row[0]), row[1])


def load_addresses(
    con: duckdb.DuckDBPyConnection, path: Path, as_of: date, commit: bool, reprocess: bool = False
) -> AddressLoad:
    """Read the voter file down to addresses; with `commit`, make it the active table.

    The same file again is a no-op unless `reprocess` (re-derive after code changes).
    """
    sha = sha256_file(path)
    found = con.execute("SELECT status FROM address_files WHERE file_id = ?", [sha]).fetchone()
    read = read_voter_addresses(con, path)
    f = read.frame
    summary = (
        sha,
        read.rows_read,
        len(f),
        int((f["precinct_codes"] > 1).sum()),
        int(f["council_district"].notna().sum()),
    )
    if found is not None and found[0] == "active" and not reprocess:
        return AddressLoad("noop", *summary)
    if not commit:
        return AddressLoad("reviewed", *summary)
    frame = f.assign(file_id=sha)
    con.execute("BEGIN")
    try:
        con.execute(
            "DELETE FROM voter_addresses WHERE file_id IN"
            " (SELECT file_id FROM address_files WHERE status = 'active')"
        )
        con.execute("UPDATE address_files SET status = 'superseded' WHERE status = 'active'")
        con.execute("DELETE FROM address_files WHERE file_id = ?", [sha])  # reprocess
        con.execute(
            "INSERT INTO address_files (file_id, filename, as_of, rows_read, addresses,"
            " status) VALUES (?, ?, ?, ?, ?, 'active')",
            [sha, path.name, as_of, read.rows_read, len(f)],
        )
        con.register("_va", frame)
        con.execute("INSERT INTO voter_addresses BY NAME SELECT * FROM _va")
        con.unregister("_va")
        con.execute("COMMIT")
    except Exception:
        con.execute("ROLLBACK")
        raise
    return AddressLoad("loaded", *summary)


def staging_dir(settings: Settings, staging_id: str) -> Path:
    return settings.data_dir / "staging" / staging_id


def stage_parcels(
    con: duckdb.DuckDBPyConnection,
    settings: Settings,
    path: Path,
    as_of: date,
    reprocess: bool = False,
) -> dict[str, Any]:
    """Read, locate, and write a review batch; returns the report. Never commits.

    An already-committed file is a no-op unless `reprocess` (re-derive after code changes).
    """
    sha = sha256_file(path)
    staging_id = f"prc-{sha[:12]}"
    found = con.execute("SELECT status FROM parcel_files WHERE file_id = ?", [sha]).fetchone()
    active = found is not None and found[0] == "active"
    if reprocess and not active:
        raise StagingError(f"{path.name}: --reprocess needs the active parcel file")
    read = read_parcels(path)
    addr = active_address_file(con)
    result = assign_parcels(con, read.frame, settings.county, as_of, addr[0] if addr else None)
    other, other_log = assign_other(con, read.frame, settings.county, as_of, result.frame)
    result.frame = result.frame.join(other, on="pid")
    result.log.extend(other_log)
    voter_units = result.frame.set_index("pid")["voter_units"]
    read.frame = estimate_apartment_units(con, settings.county, read.frame, voter_units)
    result.frame = result.frame.drop(columns=["voter_units"])
    report = build_report(
        con,
        staging_id,
        path,
        sha,
        as_of,
        read,
        result,
        addr,
        already=active and not reprocess,
    )
    report["reprocess"] = reprocess
    if report["status"] != "noop":
        _write(con, staging_dir(settings, staging_id), path, sha, as_of, read, result, addr, report)
    return report


def _write(
    con: duckdb.DuckDBPyConnection,
    directory: Path,
    path: Path,
    sha: str,
    as_of: date,
    read: Any,
    result: Any,
    addr: tuple[str, date] | None,
    report: dict[str, Any],
) -> None:
    if directory.exists():
        shutil.rmtree(directory)
    directory.mkdir(parents=True)
    frames = {
        "parcels": read.frame.assign(file_id=sha),
        "parcel_assignments": result.frame.assign(file_id=sha),
        "parcel_log": pd.DataFrame(
            read.log + result.log, columns=["pid", "issue", "detail"]
        ).assign(file_id=sha),
    }
    for name, df in frames.items():
        con.register("_stage", df)
        con.execute(f"COPY (SELECT * FROM _stage) TO '{directory / name}.parquet' (FORMAT parquet)")
        con.unregister("_stage")
    manifest = {
        "staging_id": report["staging_id"],
        "source": str(path.resolve()),
        "filename": path.name,
        "sha256": sha,
        "as_of": as_of.isoformat(),
        "adapter": ADAPTER,
        "status": report["status"],
        "address_file_id": addr[0] if addr else None,
        "row_counts": {k: len(v) for k, v in frames.items()},
        "reprocess": report.get("reprocess", False),
        "committed_at": None,
    }
    (directory / "manifest.json").write_text(json.dumps(manifest, indent=2))
    (directory / "report.json").write_text(json.dumps(report, indent=2, default=str))
    (directory / "report.txt").write_text(render(report))


def commit_parcels(
    con: duckdb.DuckDBPyConnection, settings: Settings, staging_id: str, allow_replace: bool = False
) -> str:
    directory = staging_dir(settings, staging_id)
    if not (directory / "manifest.json").exists():
        raise StagingError(f"no parcel staging batch {staging_id}")
    m = json.loads((directory / "manifest.json").read_text())
    if m["status"] != "ready":
        raise StagingError(f"{staging_id} is {m['status']}; see {directory / 'report.txt'}")
    source = Path(m["source"])
    if not source.exists() or sha256_file(source) != m["sha256"]:
        raise StagingError(f"{staging_id}: {source} is missing or changed since review")
    old = con.execute(
        "SELECT file_id, filename FROM parcel_files WHERE status = 'active'"
    ).fetchone()
    if old is not None and old[0] == m["sha256"] and not m.get("reprocess"):
        return "already committed"
    if old is not None and old[0] != m["sha256"] and not allow_replace:
        raise StagingError(f"{staging_id} would replace {old[1]}; confirm with --replace")
    raw = settings.data_dir / "raw" / f"{m['sha256'][:12]}__{m['filename']}"
    raw.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, raw)
    _commit(con, directory, m, raw, old[0] if old else None)
    stats = materialize_stats(con, m["sha256"])
    m["status"] = "committed"
    (directory / "manifest.json").write_text(json.dumps(m, indent=2))
    replaced = (
        ""
        if old is None
        else ("; reprocessed" if old[0] == m["sha256"] else f"; superseded {old[1]}")
    )
    return f"{m['row_counts']['parcels']:,} parcels, {stats:,} area statistics{replaced}"


def _commit(
    con: duckdb.DuckDBPyConnection,
    directory: Path,
    m: dict[str, Any],
    raw: Path,
    old_id: str | None,
) -> None:
    con.execute("BEGIN")
    try:
        if old_id is not None:
            for t in (*TABLES, "parcel_stats"):
                con.execute(f"DELETE FROM {t} WHERE file_id = ?", [old_id])
            if old_id == m["sha256"]:  # reprocess: same file, re-derived rows
                con.execute("DELETE FROM parcel_files WHERE file_id = ?", [old_id])
            else:
                con.execute(
                    "UPDATE parcel_files SET status = 'superseded' WHERE file_id = ?", [old_id]
                )
        con.execute(
            "INSERT INTO parcel_files (file_id, filename, stored_path, as_of, adapter,"
            " staging_id, parcels, address_file_id, status)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'active')",
            [
                m["sha256"],
                m["filename"],
                str(raw),
                m["as_of"],
                m["adapter"],
                m["staging_id"],
                m["row_counts"]["parcels"],
                m["address_file_id"],
            ],
        )
        for t in TABLES:
            con.execute(
                f"INSERT INTO {t} BY NAME SELECT * FROM read_parquet('{directory / t}.parquet')"
            )
            got = con.execute(
                f"SELECT count(*) FROM {t} WHERE file_id = ?", [m["sha256"]]
            ).fetchone()
            if got is None or got[0] != m["row_counts"][t]:
                raise StagingError(f"{t}: staged {m['row_counts'][t]} rows but {got} landed")
        con.execute("COMMIT")
    except Exception:
        con.execute("ROLLBACK")
        raise
