"""Census blocks with population: the weights for allocating split precincts."""

import logging
from pathlib import Path

import duckdb
import geopandas as gpd
import pandas as pd
import shapely

from precinctmap.registry.config import BlocksSpec
from precinctmap.registry.sources import dataset_uri, polygonal
from precinctmap.registry.store import STORE_CRS, BoundaryError

log = logging.getLogger(__name__)


def load_blocks(
    con: duckdb.DuckDBPyConnection, spec: BlocksSpec, data_dir: Path, county: str
) -> int:
    """Replace this county's blocks of `spec.vintage`. Returns the number loaded."""
    gdf = gpd.read_file(dataset_uri(data_dir / spec.source), where=spec.where)
    if gdf.empty:
        raise BoundaryError(f"no blocks read from {spec.source} (where={spec.where})")
    gdf = gdf.to_crs(STORE_CRS)
    fixed = [polygonal(g) for g in shapely.make_valid(gdf.geometry.values)]
    df = pd.DataFrame(
        {
            "geoid": gdf[spec.id_field].astype(str),
            "pop": gdf[spec.pop_field].astype("int64"),
            "housing": gdf[spec.housing_field].astype("int64"),
            "wkb": shapely.to_wkb(fixed),
        }
    )
    con.execute("BEGIN")
    try:
        con.execute(
            "DELETE FROM census_blocks WHERE county = ? AND vintage = ?", [county, spec.vintage]
        )
        con.register("_blocks", df)
        con.execute(
            "INSERT INTO census_blocks SELECT geoid, ?, ?, pop, housing, ST_GeomFromWKB(wkb)"
            " FROM _blocks",
            [spec.vintage, county],
        )
        con.unregister("_blocks")
        con.execute("COMMIT")
    except Exception:
        con.execute("ROLLBACK")
        raise
    log.info("loaded %d %s blocks (%d people)", len(df), spec.vintage, int(df["pop"].sum()))
    return len(df)


def read_blocks(con: duckdb.DuckDBPyConnection, county: str, vintage: int) -> gpd.GeoDataFrame:
    rows = con.execute(
        "SELECT geoid, pop, ST_AsWKB(geom) FROM census_blocks WHERE county = ? AND vintage = ?",
        [county, vintage],
    ).fetchall()
    if not rows:
        raise BoundaryError(f"no {vintage} census blocks loaded for {county}")
    return gpd.GeoDataFrame(
        {"geoid": [r[0] for r in rows], "pop": [r[1] for r in rows]},
        geometry=shapely.from_wkb([bytes(r[2]) for r in rows]),
        crs=STORE_CRS,
    )
