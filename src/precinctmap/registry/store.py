"""Boundary sets in the store: insert, remove, look up by date, read back as GeoDataFrames.

Geometry is stored in EPSG:4269. A set is valid on dates d with valid_from <= d < valid_to.
"""

from dataclasses import dataclass
from datetime import date

import duckdb
import geopandas as gpd
import pandas as pd
import shapely

from precinctmap.registry.config import Geography, SetSpec

STORE_CRS = 4269


class BoundaryError(RuntimeError):
    pass


@dataclass(frozen=True)
class BoundarySetRef:
    boundary_set_id: str
    valid_from: date
    valid_to: date | None
    native_from: date | None
    retroactive: bool  # the lookup date precedes native_from


@dataclass(frozen=True)
class Repair:
    feature_id: str
    issue: str
    fix: str


def fingerprint_of(con: duckdb.DuckDBPyConnection, set_id: str) -> str | None:
    row = con.execute(
        "SELECT source_sha256 FROM boundary_sets WHERE boundary_set_id = ?", [set_id]
    ).fetchone()
    return None if row is None else str(row[0])


def insert_set(
    con: duckdb.DuckDBPyConnection,
    spec: SetSpec,
    county: str,
    fingerprint: str,
    features: gpd.GeoDataFrame,
    repairs: list[Repair],
) -> None:
    """Insert a set and its features (columns feature_id, name, jurisdiction, geometry)."""
    if features["feature_id"].duplicated().any():
        dupes = features["feature_id"][features["feature_id"].duplicated()].tolist()
        raise BoundaryError(f"{spec.id}: duplicate feature ids {dupes}")
    df = pd.DataFrame(
        {
            "feature_id": features["feature_id"].astype(str),
            "name": features["name"].astype(str),
            "jurisdiction": features["jurisdiction"],
            "wkb": shapely.to_wkb(features.to_crs(STORE_CRS).geometry.values),
        }
    )
    con.execute(
        "INSERT INTO boundary_sets (boundary_set_id, geography, county, valid_from, valid_to,"
        " native_from, source, source_sha256, notes, derived_from)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            spec.id,
            spec.geography,
            county,
            spec.valid_from,
            spec.valid_to,
            spec.native_from,
            spec.source or f"derived:{spec.derive}",
            fingerprint,
            spec.notes,
            spec.derived_from,
        ],
    )
    con.register("_features", df)
    con.execute(
        "INSERT INTO features SELECT ?, feature_id, name, jurisdiction, ST_GeomFromWKB(wkb)"
        " FROM _features",
        [spec.id],
    )
    con.unregister("_features")
    _insert_codes(con, spec.id, features)
    if repairs:
        con.executemany(
            "INSERT INTO geometry_repairs VALUES (?, ?, ?, ?)",
            [[spec.id, r.feature_id, r.issue, r.fix] for r in repairs],
        )


def _insert_codes(con: duckdb.DuckDBPyConnection, set_id: str, features: gpd.GeoDataFrame) -> None:
    """Source codes (code_field) for each feature, when the set has them."""
    if "code" not in features.columns or not features["code"].notna().any():
        return
    codes = features.loc[features["code"].notna(), ["feature_id", "code"]].astype(str)
    if codes["code"].duplicated().any():
        dupes = codes["code"][codes["code"].duplicated()].tolist()
        raise BoundaryError(f"{set_id}: duplicate source codes {dupes}")
    con.executemany(
        "INSERT INTO feature_codes VALUES (?, ?, ?)",
        [[set_id, f, c] for f, c in zip(codes["feature_id"], codes["code"], strict=True)],
    )


def remove_set(con: duckdb.DuckDBPyConnection, set_id: str) -> None:
    """Delete a set with its features, repairs, and any crosswalk built on it."""
    for table, col in (
        ("features", "boundary_set_id"),
        ("feature_codes", "boundary_set_id"),
        ("geometry_repairs", "boundary_set_id"),
        ("boundary_sets", "boundary_set_id"),
    ):
        con.execute(f"DELETE FROM {table} WHERE {col} = ?", [set_id])
    for table in ("precinct_crosswalk", "crosswalk_log"):
        con.execute(
            f"DELETE FROM {table} WHERE precinct_set_id = ? OR target_set_id = ?", [set_id, set_id]
        )


def set_for(
    con: duckdb.DuckDBPyConnection, geography: Geography, county: str, on: date
) -> BoundarySetRef | None:
    """The set of `geography` whose validity window covers `on`. Overlaps are an error."""
    rows = con.execute(
        "SELECT boundary_set_id, valid_from, valid_to, native_from FROM boundary_sets"
        " WHERE geography = ? AND county = ? AND valid_from <= ?"
        " AND (valid_to IS NULL OR ? < valid_to)",
        [geography, county, on, on],
    ).fetchall()
    if len(rows) > 1:
        raise BoundaryError(f"overlapping {geography} sets for {county} on {on}: {rows}")
    if not rows:
        return None
    set_id, vf, vt, nf = rows[0]
    return BoundarySetRef(set_id, vf, vt, nf, retroactive=nf is not None and on < nf)


def feature_ids(con: duckdb.DuckDBPyConnection, set_id: str) -> set[str]:
    rows = con.execute(
        "SELECT feature_id FROM features WHERE boundary_set_id = ?", [set_id]
    ).fetchall()
    return {r[0] for r in rows}


def read_features(con: duckdb.DuckDBPyConnection, set_id: str) -> gpd.GeoDataFrame:
    """Features of a set as a GeoDataFrame in EPSG:4269."""
    rows = con.execute(
        "SELECT feature_id, name, jurisdiction, ST_AsWKB(geom) FROM features"
        " WHERE boundary_set_id = ? ORDER BY feature_id",
        [set_id],
    ).fetchall()
    if not rows:
        raise BoundaryError(f"boundary set {set_id} has no features (is it loaded?)")
    return gpd.GeoDataFrame(
        {
            "feature_id": [r[0] for r in rows],
            "name": [r[1] for r in rows],
            "jurisdiction": [r[2] for r in rows],
        },
        geometry=shapely.from_wkb([bytes(r[3]) for r in rows]),
        crs=STORE_CRS,
    )


def county_outline(con: duckdb.DuckDBPyConnection, county: str) -> shapely.Geometry:
    """Union of the loaded county set's features (the clip mask)."""
    row = con.execute(
        "SELECT boundary_set_id FROM boundary_sets WHERE geography = 'county' AND county = ?"
        " ORDER BY valid_from DESC LIMIT 1",
        [county],
    ).fetchone()
    if row is None:
        raise BoundaryError(f"no county outline loaded for {county}; list it first in the config")
    return read_features(con, row[0]).geometry.union_all()
