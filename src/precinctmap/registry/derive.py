"""Derived boundary sets: retroactive precinct merges, municipalities/townships, and wards.

Municipality/township features are exact unions of precincts by name prefix, named from TIGER
places (cities, villages) and county subdivisions (townships). Places listed in carve_places
have no precincts of their own; their TIGER shape is cut out of the host township.
"""

import re
from pathlib import Path

import geopandas as gpd
import shapely

from precinctmap.ingest.normalize import slug
from precinctmap.registry.config import SetSpec
from precinctmap.registry.sources import dataset_uri, polygonal
from precinctmap.registry.store import STORE_CRS, BoundaryError

_JURISDICTION = re.compile(r"(.+?)(?: \d{2})?-[A-Z]{1,2}")
_WARD = re.compile(r"(.+?)(?: (\d{2}))?-[A-Z]{1,2}")
_PLACE_KINDS = {"25": "city", "47": "village"}  # TIGER LSAD; 57 = CDP, not a municipality


def precinct_jurisdiction(name: str) -> str:
    """'COLUMBUS 01-A' -> 'COLUMBUS'; 'MARBLE CLIFF-A' -> 'MARBLE CLIFF'."""
    m = _JURISDICTION.fullmatch(name)
    if not m:
        raise BoundaryError(f"precinct name {name!r} has no recognizable jurisdiction prefix")
    return m.group(1)


def merge_precincts(parent: gpd.GeoDataFrame, spec: SetSpec) -> gpd.GeoDataFrame:
    """Union listed precincts into one target (e.g. HAMILTON-A <- HAMILTON-A + OBETZ-D)."""
    gdf = parent.set_index("feature_id", drop=False)
    for target, members in spec.merge.items():
        missing = [m for m in [target, *members] if m not in gdf.index]
        if missing:
            raise BoundaryError(f"{spec.id}: merge refers to missing precincts {missing}")
        merged = polygonal(shapely.union_all(gdf.loc[members].geometry.values))
        gdf = gdf.drop(index=[m for m in members if m != target])
        gdf.loc[target, "geometry"] = merged
    return gpd.GeoDataFrame(gdf.reset_index(drop=True), geometry="geometry", crs=STORE_CRS)


def _places(spec: SetSpec, data_dir: Path, county: shapely.Geometry) -> gpd.GeoDataFrame:
    assert spec.places is not None
    bbox = gpd.GeoSeries([county], crs=STORE_CRS)
    pl = gpd.read_file(dataset_uri(data_dir / spec.places), bbox=bbox).to_crs(STORE_CRS)
    pl = pl[pl["LSAD"].isin(list(_PLACE_KINDS))].copy()
    pl["kind"] = pl["LSAD"].map(_PLACE_KINDS)
    pl["geometry"] = [polygonal(g) for g in shapely.intersection(pl.geometry.values, county)]
    return pl[~pl.geometry.is_empty]


def _townships(spec: SetSpec, data_dir: Path, county: shapely.Geometry) -> dict[str, str]:
    assert spec.county_subdivisions is not None
    bbox = gpd.GeoSeries([county], crs=STORE_CRS)
    cs = gpd.read_file(dataset_uri(data_dir / spec.county_subdivisions), bbox=bbox)
    return {
        str(n).upper(): f"{n} Township"
        for n, lsad in zip(cs["NAME"], cs["LSAD"], strict=True)
        if lsad == "44"  # township
    }


def _resolve(
    prefix: str, spec: SetSpec, places: gpd.GeoDataFrame, towns: dict[str, str]
) -> tuple[str, str]:
    """Precinct name prefix -> (display name, kind)."""
    target = spec.aliases.get(prefix, prefix)
    hits = places[places["NAME"].str.upper() == target.upper()]
    in_towns = target.upper() in towns
    if len(hits) == 1 and not in_towns:
        return str(hits["NAME"].iloc[0]), str(hits["kind"].iloc[0])
    if hits.empty and in_towns:
        return towns[target.upper()], "township"
    raise BoundaryError(
        f"{spec.id}: precinct prefix {prefix!r} matches {len(hits)} places and "
        f"{'a' if in_towns else 'no'} township; add an alias in config/boundaries.toml"
    )


def precinct_jurisdictions(
    parent: gpd.GeoDataFrame, spec: SetSpec, data_dir: Path, county: shapely.Geometry
) -> gpd.GeoDataFrame:
    """Dissolve precincts by name prefix; carve listed villages out of their hosts."""
    places, towns = _places(spec, data_dir, county), _townships(spec, data_dir, county)
    work = parent.assign(prefix=[precinct_jurisdiction(n) for n in parent["feature_id"]])
    dissolved = work.dissolve(by="prefix").reset_index()
    rows = []
    for prefix, geom in zip(dissolved["prefix"], dissolved.geometry, strict=True):
        name, kind = _resolve(prefix, spec, places, towns)
        rows.append(
            {"feature_id": slug(name), "name": name, "jurisdiction": kind, "geometry": geom}
        )
    for name in spec.carve_places:
        hit = places[places["NAME"] == name]
        if len(hit) != 1:
            raise BoundaryError(f"{spec.id}: carve place {name!r} found {len(hit)} times in TIGER")
        if any(r["name"] == name for r in rows):
            raise BoundaryError(f"{spec.id}: {name} has its own precincts; do not carve it")
        cut = hit.geometry.iloc[0]
        for r in rows:
            r["geometry"] = polygonal(shapely.difference(r["geometry"], cut))
        rows.append(
            {
                "feature_id": slug(name),
                "name": name,
                "jurisdiction": str(hit["kind"].iloc[0]),
                "geometry": cut,
            }
        )
    return gpd.GeoDataFrame(rows, geometry="geometry", crs=STORE_CRS)


def precinct_ward(name: str) -> tuple[str, str | None]:
    """'COLUMBUS 01-A' -> ('COLUMBUS', '01'); 'BLENDON-A' -> ('BLENDON', None): no ward number."""
    m = _WARD.fullmatch(name)
    if not m:
        raise BoundaryError(f"precinct name {name!r} has no recognizable ward prefix")
    return m.group(1), m.group(2)


def precinct_wards(
    parent: gpd.GeoDataFrame, spec: SetSpec, data_dir: Path, county: shapely.Geometry
) -> gpd.GeoDataFrame:
    """Dissolve precincts by name prefix including the ward number: 'COLUMBUS 01-A' and
    'COLUMBUS 01-B' form 'Columbus Ward 01'. A jurisdiction whose precincts have no ward number
    ('BLENDON-A') is one area, named like its municipality ('Blendon Township'). Every precinct
    nests in exactly one ward, so ward results are always exact."""
    places, towns = _places(spec, data_dir, county), _townships(spec, data_dir, county)
    parts = [precinct_ward(n) for n in parent["feature_id"]]
    work = parent.assign(
        juris=[j for j, _ in parts],
        ward=[w or "" for _, w in parts],
    )
    dissolved = work.dissolve(by=["juris", "ward"]).reset_index()
    rows = []
    for juris, ward, geom in zip(
        dissolved["juris"], dissolved["ward"], dissolved.geometry, strict=True
    ):
        town, _ = _resolve(juris, spec, places, towns)
        name = f"{town} Ward {ward}" if ward else town
        rows.append(
            {"feature_id": slug(name), "name": name, "jurisdiction": town, "geometry": geom}
        )
    ids = [r["feature_id"] for r in rows]
    if len(set(ids)) != len(ids):
        raise BoundaryError(
            f"{spec.id}: ward names collide: {sorted({i for i in ids if ids.count(i) > 1})}"
        )
    return gpd.GeoDataFrame(rows, geometry="geometry", crs=STORE_CRS)
