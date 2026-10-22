"""Simplified GeoJSON (EPSG:4326) for one geography on one date, cached by set fingerprint.

Features carry only feature_id / name / jurisdiction; results join on feature_id in the
client (MapLibre promoteId + feature-state), so switching contests never refetches geometry.
"""

import hashlib
import json
from datetime import date
from typing import Any

import duckdb
import shapely

from precinctmap.registry.store import fingerprint_of, read_features, set_for
from precinctmap.serve.labels import (
    GEOGRAPHY_LABELS,
    RETROACTIVE_COUNCIL,
    RETROACTIVE_PRECINCTS,
    ZCTA_NOTE,
)

SERVE_CRS = 4326
SIMPLIFY_DEGREES = 0.00003  # ~3 m; small enough that shared edges show no visible gaps
GRID_DEGREES = 1e-6  # ~0.1 m coordinate rounding
SERVABLE = ("precinct", "council_district", "municipality", "zcta", "county")

_CACHE: dict[tuple[str, str, bool], tuple[str, bytes]] = {}


class GeoNotFoundError(LookupError):
    pass


def _notes(geography: str, retroactive: bool) -> list[str]:
    notes = []
    if retroactive and geography in ("precinct", "municipality"):
        notes.append(RETROACTIVE_PRECINCTS)
    if retroactive and geography == "council_district":
        notes.append(RETROACTIVE_COUNCIL)
    if geography == "zcta":
        notes.append(ZCTA_NOTE)
    return notes


def _features(con: duckdb.DuckDBPyConnection, set_id: str) -> list[dict[str, Any]]:
    gdf = read_features(con, set_id).to_crs(SERVE_CRS)
    geoms = shapely.simplify(gdf.geometry.values, SIMPLIFY_DEGREES, preserve_topology=True)
    geoms = shapely.set_precision(geoms, GRID_DEGREES)
    return [
        {
            "type": "Feature",
            "properties": {"feature_id": fid, "name": name, "jurisdiction": juris},
            "geometry": json.loads(shapely.to_geojson(g)),
        }
        for fid, name, juris, g in zip(
            gdf["feature_id"], gdf["name"], gdf["jurisdiction"], geoms, strict=True
        )
        if not g.is_empty
    ]


def geojson(
    con: duckdb.DuckDBPyConnection, geography: str, county: str, on: date
) -> tuple[str, bytes]:
    """(etag, body) for the set of `geography` valid on `on`. Raises GeoNotFoundError."""
    if geography not in SERVABLE:
        raise GeoNotFoundError(f"unknown geography {geography!r}")
    ref = set_for(con, geography, county, on)  # type: ignore[arg-type]
    if ref is None:
        raise GeoNotFoundError(f"no {geography} boundaries cover {on}")
    key = (ref.boundary_set_id, fingerprint_of(con, ref.boundary_set_id) or "", ref.retroactive)
    if key not in _CACHE:
        body = json.dumps(
            {
                "type": "FeatureCollection",
                "geography": geography,
                "label": GEOGRAPHY_LABELS[geography],
                "boundary_set_id": ref.boundary_set_id,
                "retroactive": ref.retroactive,
                "notes": _notes(geography, ref.retroactive),
                "features": _features(con, ref.boundary_set_id),
            },
            separators=(",", ":"),
        ).encode()
        _CACHE[key] = (hashlib.sha256(body).hexdigest()[:20], body)
    return _CACHE[key]


def clear_cache() -> None:
    _CACHE.clear()
