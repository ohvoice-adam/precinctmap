"""Place parcels in municipalities/townships and ZIP code areas (point-in-polygon, nearest
within MAX_NEAREST_FT as a fallback), using the boundary sets valid on the file's date.

Municipalities are built from precincts, so when the voter file moved a parcel into a precinct
of another jurisdiction, the municipality follows that precinct (its majority municipality in
the crosswalk) and the method is 'voter_address'."""

from datetime import date

import duckdb
import pandas as pd

from precinctmap.parcels.assign import MAX_NEAREST_FT, _locate, _points
from precinctmap.registry.store import read_features, set_for

OTHER_GEOGRAPHIES = ("municipality", "zcta")


def _follow_precinct(
    con: duckdb.DuckDBPyConnection, out: pd.DataFrame, assigned: pd.DataFrame, muni_set: str
) -> None:
    """Municipality of the voter-file precinct where it moved the parcel across a jurisdiction."""
    pset = str(assigned["precinct_set_id"].iloc[0])
    juris = dict(
        con.execute(
            "SELECT feature_id, jurisdiction FROM features WHERE boundary_set_id = ?", [pset]
        ).fetchall()
    )
    a = assigned.set_index("pid")
    moved = a["precinct_name"].map(juris) != a["geometry_precinct"].map(juris)
    moved &= a["precinct_method"].eq("voter_address") & a["geometry_precinct"].notna()
    if not moved.any():
        return
    majority = dict(
        con.execute(
            "SELECT precinct_name, arg_max(feature_id, split_share) FROM precinct_crosswalk"
            " WHERE precinct_set_id = ? AND target_set_id = ? GROUP BY 1",
            [pset, muni_set],
        ).fetchall()
    )
    pids = a.index[moved]
    out.loc[pids, "municipality"] = a.loc[pids, "precinct_name"].map(majority).values
    out.loc[pids, "municipality_method"] = "voter_address"


def assign_other(
    con: duckdb.DuckDBPyConnection,
    parcels: pd.DataFrame,
    county: str,
    as_of: date,
    assigned: pd.DataFrame | None = None,
) -> tuple[pd.DataFrame, list[tuple[str | None, str, str]]]:
    """pid-indexed <geo>_set_id, <geo>, <geo>_method for each geography in OTHER_GEOGRAPHIES."""
    pts = _points(parcels)
    out = pd.DataFrame(index=pd.Index(parcels["pid"], name="pid"))
    log: list[tuple[str | None, str, str]] = []
    for geo in OTHER_GEOGRAPHIES:
        ref = set_for(con, geo, county, as_of)  # type: ignore[arg-type]
        if ref is None:
            log.append((None, f"no_{geo}_set", f"no {geo} boundary set covers {as_of}"))
            out[f"{geo}_set_id"], out[geo], out[f"{geo}_method"] = None, None, "unassigned"
            continue
        polys = read_features(con, ref.boundary_set_id).to_crs(3735)
        located = _locate(pts, polys, MAX_NEAREST_FT)
        out[f"{geo}_set_id"] = ref.boundary_set_id
        out[geo] = located["feature_id"]
        out[f"{geo}_method"] = located["method"]
        out[f"{geo}_method"] = out[f"{geo}_method"].fillna("unassigned")
        if geo == "municipality" and assigned is not None:
            _follow_precinct(con, out, assigned, ref.boundary_set_id)
        for pid in out.index[out[f"{geo}_method"] == "unassigned"]:
            log.append((str(pid), f"{geo}_unassigned", f"no {geo} within {MAX_NEAREST_FT:.0f} ft"))
    return out, log
