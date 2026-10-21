"""Make the store match config/boundaries.toml.

Each set has a fingerprint: its config entry plus the sha256 of every input file plus its
parent's fingerprint. Unchanged sets are skipped; changed sets need --replace (which also
drops crosswalks built on them), so a vintage never changes silently.
"""

import hashlib
import json
import logging
from dataclasses import dataclass
from pathlib import Path

import duckdb
import geopandas as gpd

from precinctmap.registry.config import RegistryConfig, SetSpec
from precinctmap.registry.derive import (
    merge_precincts,
    precinct_jurisdiction,
    precinct_jurisdictions,
)
from precinctmap.registry.sources import read_source
from precinctmap.registry.store import (
    BoundaryError,
    Repair,
    county_outline,
    fingerprint_of,
    insert_set,
    read_features,
    remove_set,
)

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class LoadResult:
    set_id: str
    action: str  # 'loaded' | 'replaced' | 'unchanged'
    features: int
    repairs: int


def file_sha256(path: Path) -> str:
    """sha256 of a file; for a shapefile, of the .shp and all its sidecars in name order."""
    h = hashlib.sha256()
    parts = sorted(path.parent.glob(f"{path.stem}.*")) if path.suffix == ".shp" else [path]
    for p in parts:
        h.update(p.name.encode())
        with p.open("rb") as f:
            for block in iter(lambda: f.read(1 << 20), b""):
                h.update(block)
    return h.hexdigest()


def fingerprint(con: duckdb.DuckDBPyConnection, spec: SetSpec, data_dir: Path) -> str:
    h = hashlib.sha256(json.dumps(spec.as_json(), sort_keys=True).encode())
    for rel in (spec.source, spec.places, spec.county_subdivisions):
        if rel:
            h.update(file_sha256(data_dir / rel).encode())
    if spec.derived_from:
        parent = fingerprint_of(con, spec.derived_from)
        if parent is None:
            raise BoundaryError(f"{spec.id}: parent {spec.derived_from} is not loaded")
        h.update(parent.encode())
    return h.hexdigest()


def _build(
    con: duckdb.DuckDBPyConnection,
    spec: SetSpec,
    data_dir: Path,
    county: str,
    repairs: list[Repair],
) -> gpd.GeoDataFrame:
    if spec.derive is None:
        outline = county_outline(con, county) if spec.clip_to_county else None
        gdf = read_source(spec, data_dir, outline, repairs)
        if spec.geography == "precinct":
            gdf["jurisdiction"] = [precinct_jurisdiction(n) for n in gdf["feature_id"]]
        return gdf
    assert spec.derived_from is not None
    parent = read_features(con, spec.derived_from)
    if spec.derive == "merge_precincts":
        return merge_precincts(parent, spec)
    if spec.derive == "precinct_jurisdictions":
        return precinct_jurisdictions(parent, spec, data_dir, county_outline(con, county))
    raise BoundaryError(f"{spec.id}: unknown derivation {spec.derive!r}")


def load_set(
    con: duckdb.DuckDBPyConnection, spec: SetSpec, data_dir: Path, county: str, replace: bool
) -> LoadResult:
    fp = fingerprint(con, spec, data_dir)
    current = fingerprint_of(con, spec.id)
    if current == fp:
        return LoadResult(spec.id, "unchanged", 0, 0)
    if current is not None and not replace:
        raise BoundaryError(
            f"{spec.id} changed since it was loaded; rerun with --replace {spec.id}"
        )
    repairs: list[Repair] = []
    gdf = _build(con, spec, data_dir, county, repairs)
    con.execute("BEGIN")
    try:
        if current is not None:
            remove_set(con, spec.id)
        insert_set(con, spec, county, fp, gdf, repairs)
        con.execute("COMMIT")
    except Exception:
        con.execute("ROLLBACK")
        raise
    action = "replaced" if current else "loaded"
    log.info("%s %s: %d features, %d repairs", action, spec.id, len(gdf), len(repairs))
    return LoadResult(spec.id, action, len(gdf), len(repairs))


def load_registry(
    con: duckdb.DuckDBPyConnection, cfg: RegistryConfig, data_dir: Path, replace: set[str]
) -> list[LoadResult]:
    unknown = replace - {s.id for s in cfg.sets}
    if unknown:
        raise BoundaryError(f"--replace names sets not in the config: {sorted(unknown)}")
    return [load_set(con, s, data_dir, cfg.county, s.id in replace) for s in cfg.sets]
