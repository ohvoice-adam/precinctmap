"""Housing-unit estimates for apartment buildings.

The auditor file has no unit counts for apartment buildings (class C, land use 401-403).
For each 2020 census block: remainder = block housing units (HOUSING20) minus the units of
the other residential parcels in the block (1 per home or condo, 2 / 3 for two- and three-
family); the remainder is shared among the block's apartment parcels by building value.
Each estimate is at least the distinct unit numbers with a registered voter at the address,
and is kept within the land-use class's range (401: 4-19, 402: 20-39, 403: 40+). Buildings
outside every block fall back to voter units or the class median. Methods:
'census_block', 'voter_units', 'class_bound', 'class_median'.
"""

import duckdb
import geopandas as gpd
import numpy as np
import pandas as pd

from precinctmap.parcels.tenure import APARTMENT_LAND_USE
from precinctmap.registry.blocks import read_blocks

BLOCK_VINTAGE = 2020


def _blocks_of(con: duckdb.DuckDBPyConnection, county: str, parcels: pd.DataFrame) -> pd.Series:
    """pid -> 2020 block GEOID for residential parcels with a point."""
    res = parcels[parcels["residential"].fillna(False).astype(bool) & parcels["x_ft"].notna()]
    pts = gpd.GeoDataFrame(
        res[["pid"]], geometry=gpd.points_from_xy(res["x_ft"], res["y_ft"]), crs=3735
    )
    blocks = read_blocks(con, county, BLOCK_VINTAGE).to_crs(3735)
    hit = gpd.sjoin(pts, blocks[["geoid", "geometry"]], how="inner", predicate="within")
    return pd.Series(hit.drop_duplicates("pid").set_index("pid")["geoid"])


def _census_share(
    con: duckdb.DuckDBPyConnection, parcels: pd.DataFrame, block: pd.Series
) -> pd.Series:
    housing = dict(
        con.execute(
            "SELECT geoid, housing FROM census_blocks WHERE vintage = ?", [BLOCK_VINTAGE]
        ).fetchall()
    )
    df = parcels.assign(block=parcels["pid"].map(block))
    apt = df["apartment"].fillna(False).astype(bool)
    known = df[~apt & df["residential"].fillna(False)].groupby("block")["units_estimate"].sum()
    remainder = (pd.Series(housing) - known.reindex(list(housing), fill_value=0)).clip(lower=0)
    a = df[apt & df["block"].notna()].copy()
    a["w"] = a["building_value"].fillna(0).clip(lower=0)
    total_w = a.groupby("block")["w"].transform("sum")
    n = a.groupby("block")["w"].transform("size")
    a["share"] = np.where(total_w > 0, a["w"] / total_w.where(total_w > 0, 1), 1 / n)
    return (a["block"].map(remainder).fillna(0) * a["share"]).set_axis(a["pid"])


def estimate_apartment_units(
    con: duckdb.DuckDBPyConnection, county: str, parcels: pd.DataFrame, voter_units: pd.Series
) -> pd.DataFrame:
    """Return parcels with units_estimate / units_method filled for apartment rows."""
    out = parcels.copy()
    census = _census_share(con, out, _blocks_of(con, county, out))
    voters = pd.to_numeric(out["pid"].map(voter_units), errors="coerce")
    from_census = out["pid"].map(census)
    for land_use, (lo, hi) in APARTMENT_LAND_USE.items():
        rows = out["apartment"].fillna(False).astype(bool) & out["landuse"].eq(land_use)
        raw = pd.concat([from_census[rows], voters[rows]], axis=1).max(axis=1)
        clipped = raw.clip(lower=lo, upper=hi)
        census_wins = from_census[rows].fillna(-1) >= voters[rows].fillna(-1)
        bounded = ~(raw.eq(clipped) | raw.isna())
        method = pd.Series(
            np.where(bounded, "class_bound", np.where(census_wins, "census_block", "voter_units")),
            index=raw.index,
        )
        has = raw.notna()
        out.loc[raw.index[has], "units_estimate"] = clipped[has]
        out.loc[raw.index[has], "units_method"] = method[has]
        fill = float(clipped[has].median()) if has.any() else float(lo)
        missing = rows & out["units_estimate"].isna()
        out.loc[missing, "units_estimate"] = fill
        out.loc[missing, "units_method"] = "class_median"
    return out
