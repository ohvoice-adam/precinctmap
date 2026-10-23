"""A synthetic mini-county for registry tests (EPSG:3735 feet, 1000 ft cells along x).

x 0-1000 COLUMBUS 01-A | 1000-2000 COLUMBUS 01-B | 2000-3000 BLENDON-A | 3000-4000 HAMILTON-A
| 4000-5000 OBETZ-D. Council district 1 covers x 0-1400, district 2 x 1400-2000.
Wards: Columbus Ward 01 = both Columbus precincts; the rest have no ward number.
Brice (a village with no precincts) sits at x 2900-3000 inside BLENDON-A.
Block populations make COLUMBUS 01-B 30/70 between districts and BLENDON-A 90/10 Blendon/Brice.
Block groups: 390490001001 = x 0-2000 (blocks 1-3), 390490001002 = x 2000-3000, 390490002001 =
x 3000-5000; the first two share tract 39049000100.
"""

from pathlib import Path

import geopandas as gpd
from shapely.geometry import box

X0, Y0 = 1_800_000, 700_000
CRS = 3735
SQ_M_PER_SQ_FT = 0.09290304
CODES = {  # BOE PRECINCTID per precinct, as the voter file uses them
    "COLUMBUS 01-A": "01001A",
    "COLUMBUS 01-B": "01001B",
    "BLENDON-A": "03001A",
    "HAMILTON-A": "08001A",
    "OBETZ-D": "08002D",
}


def cell(x1: float, x2: float) -> object:
    return box(X0 + x1, Y0, X0 + x2, Y0 + 1000)


def _write(path: Path, rows: list[dict[str, object]], driver: str | None = None) -> None:
    gdf = gpd.GeoDataFrame(rows, geometry="geometry", crs=CRS)
    gdf.to_file(path, driver=driver) if driver else gdf.to_file(path)


def write_mini_county(data_dir: Path) -> None:
    b = data_dir / "boundaries"
    b.mkdir(parents=True, exist_ok=True)
    _write(
        b / "county.shp",
        [{"GEOID": "39049", "NAMELSAD": "Franklin County", "geometry": cell(0, 5000)}],
    )
    names = ["COLUMBUS 01-A", "COLUMBUS 01-B", "BLENDON-A", "HAMILTON-A", "OBETZ-D"]
    _write(
        b / "precincts.shp",
        [
            {"NAME": n, "PRECINCTID": CODES[n], "geometry": cell(i * 1000, (i + 1) * 1000)}
            for i, n in enumerate(names)
        ],
    )
    _write(
        b / "council.geojson",
        [{"DISTRICT": 1, "geometry": cell(0, 1400)}, {"DISTRICT": 2, "geometry": cell(1400, 2000)}],
        driver="GeoJSON",
    )
    _write(
        b / "places.shp",
        [
            {"NAME": "Columbus", "LSAD": "25", "geometry": cell(0, 2000)},
            {"NAME": "Brice", "LSAD": "47", "geometry": cell(2900, 3000)},
            {"NAME": "Obetz", "LSAD": "25", "geometry": cell(4000, 5000)},
            {"NAME": "Huber Ridge", "LSAD": "57", "geometry": cell(2000, 2500)},  # CDP: ignored
        ],
    )
    _write(
        b / "cousub.shp",
        [
            {"NAME": "Blendon", "LSAD": "44", "geometry": cell(2000, 3000)},
            {"NAME": "Hamilton", "LSAD": "44", "geometry": cell(3000, 5000)},
        ],
    )
    blocks = [  # GEOID20: tract (11) + block (4); the block's first digit is its block group
        ("390490001001001", 0, 1000, 100),
        ("390490001001002", 1000, 1400, 30),
        ("390490001001003", 1400, 2000, 70),
        ("390490001002001", 2000, 2900, 90),
        ("390490001002002", 2900, 3000, 10),
        ("390490002001001", 3000, 4000, 50),
        ("390490002001002", 4000, 5000, 50),
    ]
    _write(
        b / "blocks.shp",
        [
            {
                "GEOID20": g,
                "POP20": p,
                "HOUSING20": p // 2,
                "ALAND20": round((z - a) * 1000 * SQ_M_PER_SQ_FT),
                "COUNTYFP20": "049",
                "geometry": cell(a, z),
            }
            for g, a, z, p in blocks
        ],
    )


CONFIG = """
county = "Franklin"

[blocks]
source = "boundaries/blocks.shp"
where = "COUNTYFP20 = '049'"
vintage = 2020
id_field = "GEOID20"
pop_field = "POP20"
housing_field = "HOUSING20"

[[sets]]
id = "county"
geography = "county"
source = "boundaries/county.shp"
id_field = "GEOID"
name_template = "{NAMELSAD}"
valid_from = 2020-01-01

[[sets]]
id = "pct"
geography = "precinct"
source = "boundaries/precincts.shp"
id_field = "NAME"
code_field = "PRECINCTID"
valid_from = 2025-07-30
native_from = 2025-07-30

[[sets]]
id = "pct-retro"
geography = "precinct"
derive = "merge_precincts"
from = "pct"
merge = { "HAMILTON-A" = ["HAMILTON-A", "OBETZ-D"] }
valid_from = 2024-01-01
valid_to = 2025-07-30
native_from = 2025-07-30

[[sets]]
id = "muni"
geography = "municipality"
derive = "precinct_jurisdictions"
from = "pct"
places = "boundaries/places.shp"
county_subdivisions = "boundaries/cousub.shp"
carve_places = ["Brice"]
valid_from = 2025-07-30

[[sets]]
id = "muni-retro"
geography = "municipality"
derive = "precinct_jurisdictions"
from = "pct-retro"
places = "boundaries/places.shp"
county_subdivisions = "boundaries/cousub.shp"
carve_places = ["Brice"]
valid_from = 2024-01-01
valid_to = 2025-07-30

[[sets]]
id = "ward"
geography = "ward"
derive = "precinct_wards"
from = "pct"
places = "boundaries/places.shp"
county_subdivisions = "boundaries/cousub.shp"
valid_from = 2025-07-30
native_from = 2025-07-30

[[sets]]
id = "ward-retro"
geography = "ward"
derive = "precinct_wards"
from = "pct-retro"
places = "boundaries/places.shp"
county_subdivisions = "boundaries/cousub.shp"
valid_from = 2024-01-01
valid_to = 2025-07-30
native_from = 2025-07-30

[[sets]]
id = "council"
geography = "council_district"
source = "boundaries/council.geojson"
id_field = "DISTRICT"
name_template = "District {DISTRICT}"
jurisdiction = "COLUMBUS"
valid_from = 2023-01-01
"""
