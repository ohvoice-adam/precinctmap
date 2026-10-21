"""Read a file-backed boundary set: filter, reproject to EPSG:4269, repair, clip, name."""

from pathlib import Path

import geopandas as gpd
import shapely

from precinctmap.ingest.model import NormalizationLog
from precinctmap.ingest.normalize import precinct_name
from precinctmap.registry.config import SetSpec
from precinctmap.registry.store import STORE_CRS, BoundaryError, Repair


def dataset_uri(path: Path) -> str:
    if not path.exists():
        raise BoundaryError(f"source file missing: {path}")
    return f"zip://{path}" if path.suffix.lower() == ".zip" else str(path)


def polygonal(geom: shapely.Geometry) -> shapely.Geometry:
    """Keep only polygon parts (make_valid and clipping can emit lines and points)."""
    if isinstance(geom, shapely.Polygon | shapely.MultiPolygon):
        return geom
    parts = [
        g for g in shapely.get_parts(geom) if isinstance(g, shapely.Polygon | shapely.MultiPolygon)
    ]
    return shapely.union_all(parts) if parts else shapely.Polygon()


def repair(gdf: gpd.GeoDataFrame, ids: list[str], repairs: list[Repair]) -> gpd.GeoDataFrame:
    """make_valid every invalid geometry, logging the reason, and drop non-polygon debris."""
    geoms = gdf.geometry.values
    invalid = ~shapely.is_valid(geoms)
    for i in invalid.nonzero()[0]:
        repairs.append(Repair(ids[i], str(shapely.is_valid_reason(geoms[i])), "make_valid"))
    fixed = [polygonal(g) for g in shapely.make_valid(geoms)]
    return gdf.set_geometry(gpd.GeoSeries(fixed, index=gdf.index, crs=gdf.crs))


def _feature_ids(spec: SetSpec, gdf: gpd.GeoDataFrame) -> list[str]:
    assert spec.id_field is not None
    if spec.id_field not in gdf.columns:
        raise BoundaryError(f"{spec.id}: no {spec.id_field!r} column (have {list(gdf.columns)})")
    raw = [str(v) for v in gdf[spec.id_field]]
    if spec.geography == "precinct":
        log = NormalizationLog()
        return [precinct_name(v, f"{spec.id} {spec.id_field}", log) for v in raw]
    return raw


def read_source(
    spec: SetSpec, data_dir: Path, county_geom: shapely.Geometry | None, repairs: list[Repair]
) -> gpd.GeoDataFrame:
    """GeoDataFrame with feature_id, name, jurisdiction (filled by caller rules), geometry."""
    assert spec.source is not None
    uri = dataset_uri(data_dir / spec.source)
    bbox = None
    if spec.clip_to_county:
        if county_geom is None:
            raise BoundaryError(f"{spec.id}: clip_to_county needs the county set loaded first")
        bbox = gpd.GeoSeries([county_geom], crs=STORE_CRS)
    gdf = gpd.read_file(uri, where=spec.where, bbox=bbox)
    if gdf.empty:
        raise BoundaryError(f"{spec.id}: no features read from {spec.source} (where={spec.where})")
    if gdf.crs is None:
        raise BoundaryError(f"{spec.id}: {spec.source} has no CRS; refusing to guess")
    gdf = gdf.to_crs(STORE_CRS)
    ids = _feature_ids(spec, gdf)
    gdf = repair(gdf, ids, repairs)
    template = spec.name_template
    names = [
        template.format(**row) if template else fid
        for fid, row in zip(ids, gdf.drop(columns="geometry").to_dict("records"), strict=True)
    ]
    if spec.code_field and spec.code_field not in gdf.columns:
        raise BoundaryError(f"{spec.id}: no {spec.code_field!r} column for code_field")
    codes = [str(c) for c in gdf[spec.code_field]] if spec.code_field else None
    out = gpd.GeoDataFrame(
        {"feature_id": ids, "name": names, "jurisdiction": spec.jurisdiction, "code": codes},
        geometry=gdf.geometry.values,
        crs=STORE_CRS,
    )
    if spec.clip_to_county:
        out = _clip(out, county_geom, spec, repairs)
    return out


def _clip(
    gdf: gpd.GeoDataFrame, county_geom: shapely.Geometry, spec: SetSpec, repairs: list[Repair]
) -> gpd.GeoDataFrame:
    clipped = [polygonal(g) for g in shapely.intersection(gdf.geometry.values, county_geom)]
    gdf = gdf.set_geometry(gpd.GeoSeries(clipped, index=gdf.index, crs=STORE_CRS))
    keep = ~gdf.geometry.is_empty & (gdf.to_crs(3735).area > 1.0)  # > 1 sq ft
    for fid in gdf.loc[~keep, "feature_id"]:
        repairs.append(Repair(str(fid), "outside or touching county only", "dropped by clip"))
    if not keep.any():
        raise BoundaryError(f"{spec.id}: nothing left after clipping to the county")
    return gdf.loc[keep].reset_index(drop=True)
