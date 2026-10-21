"""Locate parcels in precincts and Columbus council districts.

Precinct: where the parcel's site address matches the voter file, the BOE's precinct for that
address wins (decision 2026-10-21). Otherwise the parcel point (EPSG:3735) inside a polygon of
the precinct set valid on `as_of`, else the nearest precinct within MAX_NEAREST_FT. Council
district (parcels whose final precinct is in Columbus): the voter file's district for the
address, else the point in a district polygon, else the nearest district. The geometry result
is always kept (geometry_precinct / geometry_council), and agreement flags compare the two.
"""

from dataclasses import dataclass, field
from datetime import date

import duckdb
import geopandas as gpd
import pandas as pd

from precinctmap.parcels.addresses import match_addresses
from precinctmap.registry.store import BoundaryError, read_features, set_for

MAX_NEAREST_FT = 500.0
AREA_CRS = 3735


@dataclass
class Assignment:
    frame: pd.DataFrame  # parcel_assignments columns except file_id
    precinct_set_id: str
    council_set_id: str | None
    log: list[tuple[str | None, str, str]] = field(default_factory=list)


def _points(parcels: pd.DataFrame) -> gpd.GeoDataFrame:
    has = parcels["x_ft"].notna() & parcels["y_ft"].notna()
    sub = parcels.loc[has, ["pid", "x_ft", "y_ft"]]
    return gpd.GeoDataFrame(
        sub[["pid"]], geometry=gpd.points_from_xy(sub["x_ft"], sub["y_ft"]), crs=AREA_CRS
    )


def _locate(pts: gpd.GeoDataFrame, polys: gpd.GeoDataFrame, max_ft: float | None) -> pd.DataFrame:
    """pid -> feature_id, method ('point_in_polygon' | 'nearest'), distance_ft."""
    hit = gpd.sjoin(pts, polys[["feature_id", "geometry"]], how="inner", predicate="within")
    hit = hit.drop_duplicates("pid")  # a point on a shared edge counts once (first polygon)
    out = pd.DataFrame(
        {
            "pid": hit["pid"],
            "feature_id": hit["feature_id"],
            "method": "point_in_polygon",
            "distance_ft": None,
        }
    )
    rest = pts[~pts["pid"].isin(out["pid"])]
    if len(rest):
        near = gpd.sjoin_nearest(
            rest,
            polys[["feature_id", "geometry"]],
            how="inner",
            max_distance=max_ft,
            distance_col="distance_ft",
        )
        near = near.drop_duplicates("pid")
        out = pd.concat(
            [
                out,
                pd.DataFrame(
                    {
                        "pid": near["pid"],
                        "feature_id": near["feature_id"],
                        "method": "nearest",
                        "distance_ft": near["distance_ft"],
                    }
                ),
            ]
        )
    return out.set_index("pid")


def _precincts(
    con: duckdb.DuckDBPyConnection, county: str, as_of: date
) -> tuple[str, gpd.GeoDataFrame]:
    ref = set_for(con, "precinct", county, as_of)
    if ref is None:
        raise BoundaryError(f"no precinct boundary set covers {as_of}")
    return ref.boundary_set_id, read_features(con, ref.boundary_set_id).to_crs(AREA_CRS)


def assign_parcels(
    con: duckdb.DuckDBPyConnection,
    parcels: pd.DataFrame,
    county: str,
    as_of: date,
    address_file_id: str | None,
) -> Assignment:
    pset, pre = _precincts(con, county, as_of)
    pts = _points(parcels)
    pct = _locate(pts, pre, MAX_NEAREST_FT)
    voter = match_addresses(con, parcels, address_file_id, pset)
    out = pd.DataFrame({"pid": parcels["pid"]}).set_index("pid")
    out["precinct_set_id"] = pset
    out["precinct_name"] = pct["feature_id"]
    out["precinct_method"] = pct["method"]
    out["precinct_distance_ft"] = pct["distance_ft"]
    out = out.join(voter)
    out["geometry_precinct"] = out["precinct_name"]
    # The voter file is the source of record wherever it has the address, unless geometry put
    # the point squarely inside the same precinct.
    differs = out["voter_precinct"] != out["precinct_name"]
    fallback = out["precinct_method"] != "point_in_polygon"
    override = out["voter_precinct"].notna() & (differs | fallback)
    out.loc[override, "precinct_name"] = out.loc[override, "voter_precinct"]
    out.loc[override, "precinct_method"] = "voter_address"
    out["precinct_method"] = out["precinct_method"].fillna("unassigned")
    juris = dict(zip(pre["feature_id"], pre["jurisdiction"], strict=True))
    result = Assignment(out, pset, None)
    _councils(con, county, as_of, pts, out, juris, result)
    _agreement(out)
    _log(out, result)
    result.frame = out.reset_index()
    return result


def _councils(
    con: duckdb.DuckDBPyConnection,
    county: str,
    as_of: date,
    pts: gpd.GeoDataFrame,
    out: pd.DataFrame,
    juris: dict[str, str],
    result: Assignment,
) -> None:
    ref = set_for(con, "council_district", county, as_of)
    out["council_district"] = None
    out["council_method"] = "not_in_columbus"
    out["geometry_council"] = None
    if ref is None:
        result.log.append((None, "no_council_set", f"no council district set covers {as_of}"))
        out["council_set_id"] = None
        return
    result.council_set_id = ref.boundary_set_id
    out["council_set_id"] = ref.boundary_set_id
    districts = read_features(con, ref.boundary_set_id).to_crs(AREA_CRS)
    city = set(districts["jurisdiction"].dropna())
    eligible = out["precinct_name"].map(juris).isin(city)
    located = _locate(pts[pts["pid"].isin(out.index[eligible])], districts, None)
    out.loc[eligible, "council_method"] = "unassigned"
    inside = located[located["method"] == "point_in_polygon"]
    out.loc[inside.index, ["council_district", "council_method"]] = list(
        zip(inside["feature_id"], ["point_in_polygon"] * len(inside), strict=True)
    )
    nearest = located[located["method"] == "nearest"]
    still = nearest.index[out.loc[nearest.index, "council_district"].isna()]
    out.loc[still, "council_district"] = nearest.loc[still, "feature_id"]
    out.loc[still, "council_method"] = "nearest"
    out["geometry_council"] = out["council_district"]
    differs = out["voter_council"] != out["council_district"]
    fallback = out["council_method"] != "point_in_polygon"
    by_voter = eligible & out["voter_council"].notna() & (differs | fallback)
    out.loc[by_voter, "council_district"] = out.loc[by_voter, "voter_council"]
    out.loc[by_voter, "council_method"] = "voter_address"


def _agreement(out: pd.DataFrame) -> None:
    out["voter_match"] = out["voter_precinct"].notna()
    out["precinct_agrees"] = (out["voter_precinct"] == out["geometry_precinct"]).where(
        out["voter_match"]
    )
    both = out["voter_council"].notna() & out["geometry_council"].notna()
    out["council_agrees"] = (out["voter_council"] == out["geometry_council"]).where(both)


def _log(out: pd.DataFrame, result: Assignment) -> None:
    """One log row per exceptional parcel (fallbacks and voter-file disagreements)."""
    pm, cm = out["precinct_method"], out["council_method"]
    rows: list[tuple[str | None, str, str]] = []
    for pid, r in out[pm == "nearest"].iterrows():
        rows.append(
            (
                str(pid),
                "precinct_nearest",
                f"{r['precinct_distance_ft']:.1f} ft outside {r['precinct_name']}",
            )
        )
    for pid in out.index[pm.eq("unassigned")]:
        rows.append((str(pid), "precinct_unassigned", "no usable point or voter address"))
    for pid, r in out[cm.isin(["unassigned", "nearest"])].iterrows():
        rows.append(
            (
                str(pid),
                f"council_{r['council_method']}",
                "Columbus parcel outside every district polygon",
            )
        )
    for pid, r in out[out["precinct_agrees"].eq(False)].iterrows():
        rows.append(
            (
                str(pid),
                "precinct_voter_override",
                f"geometry {r['geometry_precinct']} -> voter file {r['voter_precinct']}",
            )
        )
    for pid, r in out[out["council_agrees"].eq(False)].iterrows():
        rows.append(
            (
                str(pid),
                "council_voter_override",
                f"geometry {r['geometry_council']} -> voter file {r['voter_council']}",
            )
        )
    result.log.extend(rows)
