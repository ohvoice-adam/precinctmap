"""Land area of every feature: its own polygon minus TIGER area water, in square miles.

Computed directly on each feature (precinct, ward, council district, municipality, ZCTA,
county), not summed from census blocks: area and water are measured in EPSG:3735 (Ohio South,
US survey feet) and converted to square miles. Water is every polygon in the TIGER area-water
file (lakes, ponds, reservoirs, wide rivers), the same water the Census leaves out of ALAND.
Stored in area_land with the water file's sha256; a set is rebuilt when its rows are missing
(new or replaced set) or the water file changed.
"""

import logging
from dataclasses import dataclass
from pathlib import Path

import duckdb
import geopandas as gpd
import pandas as pd
import shapely

from precinctmap.ingest.staging import sha256_file
from precinctmap.registry.config import RegistryConfig, WaterSpec
from precinctmap.registry.crosswalk import AREA_CRS
from precinctmap.registry.sources import dataset_uri
from precinctmap.registry.store import BoundaryError, read_features

log = logging.getLogger(__name__)

SQ_FT_PER_SQ_MI = 5280.0**2  # US survey feet (EPSG:3735 units)


@dataclass(frozen=True)
class Water:
    polygons: gpd.GeoSeries  # EPSG:3735
    tree: shapely.STRtree
    sha256: str


@dataclass(frozen=True)
class LandSummary:
    boundary_set_id: str
    action: str  # 'built' | 'unchanged'
    features: int
    area_sqmi: float
    water_sqmi: float


def read_water(spec: WaterSpec, data_dir: Path) -> Water:
    path = data_dir / spec.source
    if not path.exists():
        raise BoundaryError(f"area-water file {path} is missing (see config/boundaries.toml)")
    gdf = gpd.read_file(dataset_uri(path), where=spec.where)
    if gdf.empty:
        raise BoundaryError(f"no water polygons read from {spec.source}")
    geoms = gpd.GeoSeries(shapely.make_valid(gdf.geometry.values), crs=gdf.crs).to_crs(AREA_CRS)
    geoms = geoms[~geoms.is_empty].reset_index(drop=True)
    return Water(geoms, shapely.STRtree(geoms.values), sha256_file(path))


def land_areas(features: gpd.GeoDataFrame, water: Water) -> pd.DataFrame:
    """feature_id, area_sqmi, water_sqmi, land_sqmi for each feature (any CRS in)."""
    geoms = features.to_crs(AREA_CRS).geometry.values
    rows = []
    for fid, geom in zip(features["feature_id"], geoms, strict=True):
        hits = water.tree.query(geom, predicate="intersects")
        wet = (
            shapely.intersection(geom, shapely.union_all(water.polygons.values[hits])).area
            if len(hits)
            else 0.0
        )
        area = float(geom.area)
        rows.append((fid, area / SQ_FT_PER_SQ_MI, wet / SQ_FT_PER_SQ_MI))
    out = pd.DataFrame(rows, columns=["feature_id", "area_sqmi", "water_sqmi"])
    out["land_sqmi"] = (out["area_sqmi"] - out["water_sqmi"]).clip(lower=0.0)
    return out


def _current(con: duckdb.DuckDBPyConnection, set_id: str) -> tuple[int, set[str]]:
    rows = con.execute(
        "SELECT count(*), list(DISTINCT water_sha256) FROM area_land WHERE boundary_set_id = ?",
        [set_id],
    ).fetchone()
    return (int(rows[0]), set(rows[1] or [])) if rows else (0, set())


def build_land(
    con: duckdb.DuckDBPyConnection, cfg: RegistryConfig, data_dir: Path, force: bool = False
) -> list[LandSummary]:
    """Make area_land cover every loaded boundary set; returns one summary per set."""
    if cfg.water is None:
        raise BoundaryError("config/boundaries.toml has no [water] section")
    water = read_water(cfg.water, data_dir)
    out = []
    for (set_id,) in con.execute("SELECT boundary_set_id FROM boundary_sets ORDER BY 1").fetchall():
        features = read_features(con, set_id)
        n, shas = _current(con, set_id)
        if not force and n == len(features) and shas == {water.sha256}:
            out.append(LandSummary(set_id, "unchanged", n, 0.0, 0.0))
            continue
        land = land_areas(features, water).assign(boundary_set_id=set_id, water_sha256=water.sha256)
        con.execute("BEGIN")
        try:
            con.execute("DELETE FROM area_land WHERE boundary_set_id = ?", [set_id])
            con.register("_land", land)
            con.execute("INSERT INTO area_land BY NAME SELECT * FROM _land")
            con.unregister("_land")
            con.execute("COMMIT")
        except Exception:
            con.execute("ROLLBACK")
            raise
        summary = LandSummary(
            set_id,
            "built",
            len(land),
            float(land["area_sqmi"].sum()),
            float(land["water_sqmi"].sum()),
        )
        log.info("land %s: %d features, %.2f sq mi, %.2f water", set_id, *_nums(summary))
        out.append(summary)
    return out


def _nums(s: LandSummary) -> tuple[int, float, float]:
    return s.features, s.area_sqmi, s.water_sqmi
