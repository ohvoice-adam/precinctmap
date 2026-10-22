"""Stage a results file: parse, identify, check, and write a review report. Never commits.

Layout of data/staging/<staging_id>/: manifest.json, report.json, report.txt, source copy,
and one parquet file per catalog table (only when the election is identified).
"""

import hashlib
import json
import shutil
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd

from precinctmap.catalog.calendar import ElectionType
from precinctmap.config import Settings
from precinctmap.ingest.checks import BoundaryMatch, boundary_match, long_format_check
from precinctmap.ingest.combine import combine
from precinctmap.ingest.detect import parse_file
from precinctmap.ingest.errors import StagingError
from precinctmap.ingest.identify import identify
from precinctmap.ingest.report import Report, ReviewInputs, build_report
from precinctmap.ingest.report_text import render
from precinctmap.ingest.tables import Tables, build_tables
from precinctmap.ingest.votefor import infer_vote_for


@dataclass(frozen=True)
class Staged:
    staging_id: str
    directory: Path
    report: Report


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def staging_dir(settings: Settings, staging_id: str) -> Path:
    return settings.data_dir / "staging" / staging_id


def stage_file(
    con: duckdb.DuckDBPyConnection,
    settings: Settings,
    path: Path,
    override_date: date | None = None,
    override_type: ElectionType | None = None,
    override_certified: bool | None = None,
    reprocess: bool = False,
) -> Staged:
    """Parse `path` and write a review batch.

    A file already committed is a no-op unless `reprocess`, which re-derives its rows (after a
    correction-table or adapter change) and replaces them on commit.
    """
    sha = sha256_file(path)
    staging_id = f"stg-{sha[:12]}"
    parsed = parse_file(path)
    ident = identify(path.name, parsed, override_date, override_type, override_certified)
    parsed = combine(parsed, ident.election_id)  # reviewed combined contests (combine.py)
    vote_for = infer_vote_for(parsed)
    match = boundary_match(con, parsed, ident.election_date)
    election_id = ident.election_id
    tables = build_tables(parsed, election_id, sha, vote_for) if election_id else None
    found = _already_ingested(con, sha)
    if reprocess and (found is None or found["status"] != "active"):
        raise StagingError(f"{path.name}: --reprocess needs an active ingested file, found {found}")
    already = None if reprocess else found
    report = build_report(
        ReviewInputs(
            staging_id=staging_id,
            filename=path.name,
            sha256=sha,
            parsed=parsed,
            ident=ident,
            vote_for=vote_for,
            long_check=long_format_check(parsed),
            match=match,
            contest_ids=_contest_ids(tables),
            already_ingested=already,
            reprocessing=found if reprocess else None,
            replaces=_predecessor(con, election_id, sha) if election_id else None,
        )
    )
    directory = staging_dir(settings, staging_id)
    if already is None:
        frames = tables.as_dict() if tables is not None else {}
        if tables is not None and match.boundary_set_id:
            frames["unmatched_precincts"] = _unmatched(match, election_id or "", sha)
        _write(con, directory, path, report, frames)
    return Staged(staging_id, directory, report)


def _contest_ids(tables: Tables | None) -> dict[int, str]:
    if tables is None:
        return {}
    c = tables.contests
    return dict(zip(c["source_ordinal"], c["contest_id"], strict=True))


def _already_ingested(con: duckdb.DuckDBPyConnection, sha: str) -> dict[str, str] | None:
    row = con.execute(
        "SELECT file_id, election_id, status FROM source_files WHERE sha256 = ?", [sha]
    ).fetchone()
    return None if row is None else {"file_id": row[0], "election_id": row[1], "status": row[2]}


def _predecessor(
    con: duckdb.DuckDBPyConnection, election_id: str, sha: str
) -> dict[str, Any] | None:
    row = con.execute(
        "SELECT f.file_id, f.filename, f.ingested_at,"
        " (SELECT count(*) FROM contests c WHERE c.file_id = f.file_id),"
        " (SELECT coalesce(sum(votes), 0) FROM precinct_results r WHERE r.file_id = f.file_id)"
        " FROM source_files f WHERE f.election_id = ? AND f.status = 'active' AND f.sha256 <> ?",
        [election_id, sha],
    ).fetchone()
    if row is None:
        return None
    return {
        "file_id": row[0],
        "filename": row[1],
        "ingested_at": str(row[2]),
        "contests": int(row[3]),
        "precinct_votes": int(row[4]),
    }


def _unmatched(match: BoundaryMatch, election_id: str, file_id: str) -> pd.DataFrame:
    rows = [(n, "results_only") for n in match.results_only] + [
        (n, "boundary_only") for n in match.boundary_only
    ]
    return pd.DataFrame(
        {
            "file_id": file_id,
            "election_id": election_id,
            "boundary_set_id": match.boundary_set_id,
            "precinct_name": [n for n, _ in rows],
            "side": [s for _, s in rows],
        },
        columns=["file_id", "election_id", "boundary_set_id", "precinct_name", "side"],
    )


def _write(
    con: duckdb.DuckDBPyConnection,
    directory: Path,
    source: Path,
    report: Report,
    frames: dict[str, pd.DataFrame],
) -> None:
    if directory.exists():
        shutil.rmtree(directory)
    directory.mkdir(parents=True)
    source_copy = directory / f"source{source.suffix.lower()}"
    shutil.copy2(source, source_copy)
    for name, df in frames.items():
        con.register("_stage", df)
        con.execute(f"COPY (SELECT * FROM _stage) TO '{directory / name}.parquet' (FORMAT parquet)")
        con.unregister("_stage")
    manifest = {
        "staging_id": report["staging_id"],
        "filename": report["filename"],
        "sha256": report["sha256"],
        "source_copy": source_copy.name,
        "adapter": report["adapter"],
        "status": report["status"],
        "election": report["election"],
        "boundary_set_id": report["boundary_match"]["boundary_set_id"],
        "row_counts": {name: len(df) for name, df in frames.items()},
        "precinct_rows": report["precincts"]["rows"],
        "created_at": datetime.now(UTC).isoformat(),
        "committed_at": None,
        "reprocess": report["reprocessing"] is not None,
    }
    (directory / "manifest.json").write_text(json.dumps(manifest, indent=2))
    (directory / "report.json").write_text(json.dumps(report, indent=2, default=str))
    (directory / "report.txt").write_text(render(report))
