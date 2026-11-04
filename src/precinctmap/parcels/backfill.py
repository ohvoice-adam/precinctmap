"""Place the parcels already in the store into geographies added after they were loaded.

Parcels keep their auditor point (x_ft, y_ft in EPSG:3735), so a new geography needs no source
file: locate every active parcel file's points in the sets valid on that file's as-of date and
update parcel_assignments. Run `parcels stats` (or let this call it) to rebuild area statistics.
"""

import logging
from dataclasses import dataclass
from datetime import date

import duckdb
import pandas as pd

from precinctmap.parcels.geos import DISTRICT_GEOGRAPHIES, assign_other
from precinctmap.parcels.stats import materialize_stats

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Backfilled:
    file_id: str
    filename: str
    parcels: int
    placed: dict[str, int]  # geography -> parcels with a district
    stat_rows: int


def backfill_districts(con: duckdb.DuckDBPyConnection, county: str) -> list[Backfilled]:
    """Add Ohio House/Senate districts to every active parcel file, then rebuild its statistics."""
    files = con.execute(
        "SELECT file_id, filename, as_of FROM parcel_files WHERE status = 'active'"
    ).fetchall()
    return [_one(con, county, str(fid), str(name), as_of) for fid, name, as_of in files]


def _one(
    con: duckdb.DuckDBPyConnection, county: str, fid: str, name: str, as_of: date
) -> Backfilled:
    parcels = con.execute("SELECT pid, x_ft, y_ft FROM parcels WHERE file_id = ?", [fid]).df()
    placed, issues = assign_other(
        con,
        parcels,
        county,
        as_of,
        None,
        DISTRICT_GEOGRAPHIES,
    )
    cols = [f"{g}{suffix}" for g in DISTRICT_GEOGRAPHIES for suffix in ("_set_id", "", "_method")]
    frame = placed[cols].reset_index()
    con.execute("BEGIN")
    try:
        con.register("_districts", frame)
        sets = ", ".join(f"{c} = d.{c}" for c in cols)
        con.execute(
            f"UPDATE parcel_assignments SET {sets} FROM _districts d"
            " WHERE parcel_assignments.file_id = ? AND parcel_assignments.pid = d.pid",
            [fid],
        )
        con.unregister("_districts")
        con.execute("DELETE FROM parcel_log WHERE file_id = ? AND issue LIKE 'state_%'", [fid])
        if issues:
            log_frame = pd.DataFrame(issues, columns=["pid", "issue", "detail"]).assign(file_id=fid)
            con.register("_plog", log_frame)
            con.execute("INSERT INTO parcel_log BY NAME SELECT * FROM _plog")
            con.unregister("_plog")
        con.execute("COMMIT")
    except Exception:
        con.execute("ROLLBACK")
        log.exception("backfilling districts for %s failed", name)
        raise
    counts = {g: int(placed[g].notna().sum()) for g in DISTRICT_GEOGRAPHIES}
    return Backfilled(fid, name, len(parcels), counts, materialize_stats(con, fid))
