"""Fetch, review and commit an ACS 5-year release (staged, like every other ingest).

`fetch_release` downloads each table and keeps the county's rows under
data/raw/census/acs5-<year>/. `review_release` computes every measure from those files and
reports what it found (units, county checks, placement, fallbacks) without writing.
`commit_release` writes the release, its files (sha256) and the statistics; recommitting the
same files is a no-op, and different files replace the release and log it.
"""

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import duckdb
import pandas as pd

from precinctmap.census.blocks import assign_blocks, read_land_area
from precinctmap.census.measures import Computed, compute, unplaced_units
from precinctmap.census.summary_file import (
    BASE_URL,
    TableData,
    TableFile,
    describe,
    fetch_table,
    file_name,
    read_table,
    table_url,
)
from precinctmap.census.tables import TABLES, level_of
from precinctmap.registry.config import RegistryConfig
from precinctmap.registry.store import BoundaryError, read_features, set_for


def release_id(year: int) -> str:
    return f"acs5-{year}"


def release_label(year: int) -> str:
    return f"ACS {year - 4}-{year} 5-year estimates"


def release_dir(data_dir: Path, year: int) -> Path:
    return data_dir / "raw" / "census" / release_id(year)


def county_fips(con: duckdb.DuckDBPyConnection, county: str, as_of: date) -> str:
    """The county's 5-digit FIPS code: the feature_id of its county outline."""
    ref = set_for(con, "county", county, as_of)
    if ref is None:
        raise BoundaryError(f"no county outline for {county} on {as_of}")
    ids = read_features(con, ref.boundary_set_id)["feature_id"].tolist()
    if len(ids) != 1 or len(ids[0]) != 5:
        raise BoundaryError(f"county set {ref.boundary_set_id} should hold one 5-digit GEOID")
    return str(ids[0])


def fetch_release(
    data_dir: Path, year: int, fips: str, base_url: str = BASE_URL
) -> list[TableFile]:
    return [fetch_table(year, t, fips, release_dir(data_dir, year), base_url) for t in TABLES]


@dataclass
class CensusReview:
    release_id: str
    label: str
    year: int
    as_of: date
    files: list[TableFile]
    county_checks: list[tuple[str, float, float]]  # table, sum of units, published county
    placed: dict[str, int]  # geography -> blocks with a feature
    blocks: int
    computed: Computed
    log: list[tuple[str, str]] = field(default_factory=list)


def _read_files(data_dir: Path, year: int) -> tuple[list[TableFile], dict[str, TableData]]:
    files, tables = [], {}
    for t in TABLES:
        path = release_dir(data_dir, year) / file_name(year, t)
        if not path.exists():
            raise FileNotFoundError(f"{path} is missing; run `precinctmap census fetch` first")
        files.append(describe(path, t, table_url(year, t)))
        tables[t] = read_table(path, t, level_of(t))
    return files, tables


def review_release(
    con: duckdb.DuckDBPyConnection, cfg: RegistryConfig, data_dir: Path, year: int, as_of: date
) -> CensusReview:
    files, tables = _read_files(data_dir, year)
    land = read_land_area(cfg.blocks, data_dir)
    assigned = assign_blocks(con, cfg.county, cfg.blocks.vintage, as_of, land)
    computed = compute(tables, assigned)
    checks = [
        (t, float(d.estimates[1].sum()), float(d.county_estimates[1])) for t, d in tables.items()
    ]
    blocks = assigned.blocks
    placed = {g: int(blocks[g].notna().sum()) for g in assigned.set_ids}
    log = assigned.log + computed.log + unplaced_units(tables, blocks)
    for t, units, county in checks:
        if abs(units - county) > 0.5:
            log.append(
                ("county_total_differs", f"{t}: units sum {units:,.0f}, county {county:,.0f}")
            )
    return CensusReview(
        release_id(year),
        release_label(year),
        year,
        as_of,
        files,
        checks,
        placed,
        len(blocks),
        computed,
        log,
    )


def _same_files(con: duckdb.DuckDBPyConnection, review: CensusReview) -> bool:
    have = dict(
        con.execute(
            "SELECT table_id, sha256 FROM census_files WHERE release_id = ?", [review.release_id]
        ).fetchall()
    )
    return have == {f.table: f.sha256 for f in review.files}


def commit_release(con: duckdb.DuckDBPyConnection, review: CensusReview, county: str) -> str:
    """Write the release; returns 'noop', 'committed' or 'replaced'."""
    rid = review.release_id
    exists = con.execute(
        "SELECT count(*) FROM census_releases WHERE release_id = ?", [rid]
    ).fetchone()
    replacing = bool(exists and exists[0])
    if replacing and _same_files(con, review):
        return "noop"
    files = pd.DataFrame(
        [
            (rid, f.table, f.path.name, f.source_url, f.sha256, f.block_groups or f.tracts)
            for f in review.files
        ],
        columns=["release_id", "table_id", "filename", "source_url", "sha256", "block_groups"],
    )
    stats = review.computed.stats.assign(release_id=rid)
    log = pd.DataFrame(review.log or [], columns=["issue", "detail"]).assign(release_id=rid)
    if replacing:
        log = pd.concat(
            [log, pd.DataFrame([{"release_id": rid, "issue": "replaced", "detail": "new files"}])]
        )
    con.execute("BEGIN")
    try:
        for table in ("census_stats", "census_files", "census_log", "census_releases"):
            con.execute(f"DELETE FROM {table} WHERE release_id = ?", [rid])
        con.execute(
            "INSERT INTO census_releases (release_id, label, year_start, year_end, county, as_of)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            [rid, review.label, review.year - 4, review.year, county, review.as_of],
        )
        for name, frame in (("census_files", files), ("census_stats", stats), ("census_log", log)):
            con.register("_c", frame)
            con.execute(f"INSERT INTO {name} BY NAME SELECT * FROM _c")
            con.unregister("_c")
        con.execute("COMMIT")
    except Exception:
        con.execute("ROLLBACK")
        raise
    return "replaced" if replacing else "committed"
