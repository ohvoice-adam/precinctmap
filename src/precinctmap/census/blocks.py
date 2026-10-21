"""2020 blocks as the bridge from block groups to every geography.

Each block belongs to the block group (tract) named by the first 12 (11) digits of its GEOID.
Each block counts in the feature of every geography that holds its interior point (EPSG:3735),
using the boundary sets valid on `as_of`; a point outside every polygon goes to the nearest feature
within MAX_NEAREST_FT. Council districts take only blocks whose precinct is in the city the
districts belong to, and each such block gets its nearest district if it is in none, as for
parcels. Land area comes from the TIGER block file (ALAND20).
"""

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import duckdb
import geopandas as gpd
import pandas as pd
import pyogrio
import shapely

from precinctmap.parcels.assign import AREA_CRS, MAX_NEAREST_FT, _locate
from precinctmap.registry.config import BlocksSpec
from precinctmap.registry.sources import dataset_uri
from precinctmap.registry.store import STORE_CRS, BoundaryError, read_features, set_for

GEOGRAPHIES = ("precinct", "council_district", "municipality", "zcta")
ALAND_FIELD = "ALAND20"
SQ_M_PER_SQ_MI = 2_589_988.110336


@dataclass
class BlockAssignment:
    blocks: pd.DataFrame  # index geoid: block_group, tract, pop, housing, land_sqmi, <geo> ids
    set_ids: dict[str, str]  # geography -> boundary_set_id
    log: list[tuple[str, str]] = field(default_factory=list)  # (issue, detail)


def read_land_area(spec: BlocksSpec, data_dir: Path) -> pd.Series:
    """Block GEOID -> land area in square miles, from the TIGER block file."""
    # All attributes, no geometry: the `where` filter may name columns beyond these two.
    df = pyogrio.read_dataframe(
        dataset_uri(data_dir / spec.source), where=spec.where, read_geometry=False
    )
    if ALAND_FIELD not in df.columns:
        raise BoundaryError(f"{spec.source} has no {ALAND_FIELD} column")
    return pd.Series(
        df[ALAND_FIELD].astype(float).to_numpy() / SQ_M_PER_SQ_MI,
        index=df[spec.id_field].astype(str),
    )


def _blocks(con: duckdb.DuckDBPyConnection, county: str, vintage: int) -> gpd.GeoDataFrame:
    rows = con.execute(
        "SELECT geoid, pop, housing, ST_AsWKB(geom) FROM census_blocks"
        " WHERE county = ? AND vintage = ? ORDER BY geoid",
        [county, vintage],
    ).fetchall()
    if not rows:
        raise BoundaryError(f"no {vintage} census blocks loaded for {county}")
    gdf = gpd.GeoDataFrame(
        {
            "pid": [r[0] for r in rows],  # `_locate` keys points by `pid`
            "pop": [float(r[1]) for r in rows],
            "housing": [float(r[2]) for r in rows],
        },
        geometry=shapely.from_wkb([bytes(r[3]) for r in rows]),
        crs=STORE_CRS,
    ).to_crs(AREA_CRS)
    gdf["geometry"] = gdf.geometry.representative_point()
    return gdf


def _place(
    con: duckdb.DuckDBPyConnection,
    pts: gpd.GeoDataFrame,
    set_id: str,
    out: BlockAssignment,
    geo: str,
) -> pd.Series:
    limit = None if geo == "council_district" else MAX_NEAREST_FT  # every city block gets one
    located = _locate(pts, read_features(con, set_id).to_crs(AREA_CRS), limit)
    near = int((located["method"] == "nearest").sum())
    if near:
        out.log.append((f"{geo}_nearest", f"{near} block points placed in the nearest {geo}"))
    return located["feature_id"].reindex(pts["pid"]).set_axis(pts.index)


def assign_blocks(
    con: duckdb.DuckDBPyConnection, county: str, vintage: int, as_of: date, land: pd.Series
) -> BlockAssignment:
    """Blocks with their block group, weights, land area and a feature per geography."""
    pts = _blocks(con, county, vintage)
    frame = pd.DataFrame(
        {
            "block_group": pts["pid"].str[:12],
            "tract": pts["pid"].str[:11],
            "pop": pts["pop"],
            "housing": pts["housing"],
        }
    ).set_axis(pts["pid"])
    frame["land_sqmi"] = land.reindex(frame.index)
    out = BlockAssignment(frame, {})
    if frame["land_sqmi"].isna().any():
        missing = int(frame["land_sqmi"].isna().sum())
        out.log.append(("land_area_missing", f"{missing} blocks lack {ALAND_FIELD}; counted as 0"))
        frame["land_sqmi"] = frame["land_sqmi"].fillna(0.0)
    pts = pts.set_index("pid", drop=False).rename_axis(None)  # sjoin needs the name free
    for geo in GEOGRAPHIES:
        ref = set_for(con, geo, county, as_of)  # type: ignore[arg-type]
        if ref is None:
            out.log.append((f"no_{geo}_set", f"no {geo} boundary set covers {as_of}"))
            continue
        out.set_ids[geo] = ref.boundary_set_id
        subset = pts
        if geo == "council_district" and "precinct" in out.set_ids:
            subset = pts[_in_city(con, out, ref.boundary_set_id)]
        frame[geo] = _place(con, subset, ref.boundary_set_id, out, geo).reindex(frame.index)
        unplaced = frame.index[frame[geo].isna() & frame.index.isin(subset.index)]
        if len(unplaced):
            out.log.append((f"{geo}_unassigned", f"{len(unplaced)} blocks outside every {geo}"))
    return out


def _in_city(con: duckdb.DuckDBPyConnection, out: BlockAssignment, council_set: str) -> pd.Series:
    """Blocks whose precinct belongs to the jurisdiction the council districts cover."""
    juris = dict(
        con.execute(
            "SELECT feature_id, jurisdiction FROM features WHERE boundary_set_id = ?",
            [out.set_ids["precinct"]],
        ).fetchall()
    )
    city = {
        j
        for (j,) in con.execute(
            "SELECT DISTINCT jurisdiction FROM features WHERE boundary_set_id = ?"
            " AND jurisdiction IS NOT NULL",
            [council_set],
        ).fetchall()
    }
    return out.blocks["precinct"].map(juris).isin(city)
