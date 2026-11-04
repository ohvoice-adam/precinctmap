"""State legislative districts: the real config's vintage windows, and sliver clipping."""

from datetime import date
from pathlib import Path

import geopandas as gpd
import pytest
from shapely.geometry import box

from precinctmap.registry.config import DEFAULT_CONFIG, SetSpec, load_config
from precinctmap.registry.sources import read_source
from precinctmap.registry.store import BoundaryError

CHAMBERS = ("state_house", "state_senate")


def _covering(geo: str, on: date) -> list[str]:
    cfg = load_config(DEFAULT_CONFIG)
    return [
        s.id
        for s in cfg.sets
        if s.geography == geo and s.valid_from <= on and (s.valid_to is None or on < s.valid_to)
    ]


@pytest.mark.parametrize("geo", CHAMBERS)
@pytest.mark.parametrize(
    ("on", "vintage"),
    [
        (date(2016, 11, 8), "2011"),
        (date(2020, 11, 3), "2011"),
        (date(2022, 5, 3), "2011"),  # May 2022 primary: no legislative races, old map
        (date(2022, 8, 2), "2022"),  # first election on the 2022 map
        (date(2022, 11, 8), "2022"),
        (date(2023, 11, 7), "2022"),
        (date(2024, 3, 19), "2024"),  # first election on the 2024 map
        (date(2026, 11, 3), "2024"),
    ],
)
def test_exactly_one_map_covers_each_election_date(geo, on, vintage):
    covering = _covering(geo, on)
    assert len(covering) == 1, covering
    assert covering[0].endswith(vintage)


@pytest.mark.parametrize("geo", CHAMBERS)
def test_state_sets_are_clipped_and_drop_the_unassigned_placeholder(geo):
    for s in (s for s in load_config(DEFAULT_CONFIG).sets if s.geography == geo):
        assert s.clip_to_county
        assert s.min_area_sqmi and s.min_area_sqmi > 0
        assert s.where and "ZZZ" in s.where  # TIGER's 'undefined' district


def test_clip_drops_slivers_but_keeps_real_districts(tmp_path: Path):
    data = tmp_path / "boundaries"
    data.mkdir()
    # EPSG:3735 feet. County is 10,000 x 10,000 ft (3.6 sq mi); district 001 fills most of it,
    # 002 is a 100 x 100 ft corner (0.0004 sq mi).
    county = box(0, 0, 10_000, 10_000)
    gpd.GeoDataFrame(
        {"SLDLST": ["001", "002"]},
        geometry=[box(-500, -500, 9_900, 10_500), box(9_900, 9_900, 20_000, 20_000)],
        crs=3735,
    ).to_file(data / "d.shp")
    outline = gpd.GeoSeries([county], crs=3735).to_crs(4269).iloc[0]

    def spec(min_area: float | None) -> SetSpec:
        return SetSpec(
            id="t",
            geography="state_house",
            valid_from=date(2000, 1, 1),
            source="boundaries/d.shp",
            id_field="SLDLST",
            name_template="House District {SLDLST}",
            clip_to_county=True,
            min_area_sqmi=min_area,
        )

    kept = read_source(spec(None), tmp_path, outline, [])
    assert sorted(kept["feature_id"]) == ["001", "002"]  # without the cutoff the corner stays
    repairs: list = []
    out = read_source(spec(0.05), tmp_path, outline, repairs)
    assert list(out["feature_id"]) == ["001"]
    assert list(out["name"]) == ["House District 001"]
    assert [r.feature_id for r in repairs if r.fix == "dropped by clip"] == ["002"]


def test_clip_with_nothing_left_raises(tmp_path: Path):
    (tmp_path / "boundaries").mkdir()
    gpd.GeoDataFrame({"SLDLST": ["001"]}, geometry=[box(0, 0, 100, 100)], crs=3735).to_file(
        tmp_path / "boundaries" / "d.shp"
    )
    outline = gpd.GeoSeries([box(50_000, 50_000, 60_000, 60_000)], crs=3735).to_crs(4269).iloc[0]
    s = SetSpec(
        id="t",
        geography="state_house",
        valid_from=date(2000, 1, 1),
        source="boundaries/d.shp",
        id_field="SLDLST",
        clip_to_county=True,
    )
    with pytest.raises(BoundaryError):
        read_source(s, tmp_path, outline, [])
