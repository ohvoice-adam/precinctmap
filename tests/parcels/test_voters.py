from datetime import date

import geopandas as gpd
import pytest
from shapely.geometry import box

from precinctmap.parcels.ingest import commit_parcels, load_addresses, stage_parcels
from precinctmap.parcels.voters import refresh_voter_stats
from precinctmap.registry.config import load_config
from precinctmap.registry.land import SQ_FT_PER_SQ_MI, build_land
from tests.fixtures.geo import CONFIG, CRS, X0, Y0
from tests.fixtures.parcels import write_parcel_csv, write_voter_file

AS_OF = date(2026, 10, 21)
CELL_SQMI = 1000 * 1000 / SQ_FT_PER_SQ_MI  # one mini-county precinct


def _with_water(settings, tmp_path):
    """Water: the west half of COLUMBUS 01-A, plus a pond outside every precinct."""
    gpd.GeoDataFrame(
        {"HYDROID": ["1", "2"]},
        geometry=[box(X0, Y0, X0 + 500, Y0 + 1000), box(X0 - 900, Y0, X0 - 800, Y0 + 100)],
        crs=CRS,
    ).to_file(settings.data_dir / "boundaries" / "water.shp")
    path = tmp_path / "boundaries-water.toml"
    path.write_text(CONFIG + '\n[water]\nsource = "boundaries/water.shp"\nvintage = 2026\n')
    return load_config(path)


@pytest.fixture
def voters(registry, seeded, settings, tmp_path):
    """Mini-county with the 2025 general, land areas and a committed parcel file."""
    con, _, _ = registry
    build_land(con, _with_water(settings, tmp_path), settings.data_dir)
    load_addresses(con, write_voter_file(tmp_path / "VOTERFILE.TXT"), AS_OF, commit=True)
    report = stage_parcels(con, settings, write_parcel_csv(tmp_path / "Parcel.csv"), AS_OF)
    commit_parcels(con, settings, report["staging_id"])
    return con


def _land(con, fid):
    return con.execute(
        "SELECT area_sqmi, water_sqmi, land_sqmi FROM area_land l JOIN boundary_sets b"
        " USING (boundary_set_id) WHERE b.geography = 'precinct' AND l.feature_id = ?",
        [fid],
    ).fetchone()


def test_land_is_each_polygon_minus_its_water(registry, settings, tmp_path):
    con, _, _ = registry
    cfg = _with_water(settings, tmp_path)
    built = build_land(con, cfg, settings.data_dir)
    assert {s.action for s in built} == {"built"}
    area, water, land = _land(con, "COLUMBUS 01-A")
    assert area == pytest.approx(CELL_SQMI)
    assert water == pytest.approx(CELL_SQMI / 2)  # the pond outside the county counts nowhere
    assert land == pytest.approx(CELL_SQMI / 2)
    assert _land(con, "COLUMBUS 01-B") == pytest.approx((CELL_SQMI, 0.0, CELL_SQMI))
    assert {s.action for s in build_land(con, cfg, settings.data_dir)} == {"unchanged"}
    assert {s.action for s in build_land(con, cfg, settings.data_dir, force=True)} == {"built"}


def _stat(con, geo, fid, metric):
    return con.execute(
        "SELECT value, n FROM parcel_stats WHERE geography = ? AND feature_id = ? AND metric = ?",
        [geo, fid, metric],
    ).fetchone()


def _registered(con, fid):
    row = con.execute(
        "SELECT registered FROM precinct_turnout WHERE party = 'ALL' AND precinct_name = ?", [fid]
    ).fetchone()
    return float(row[0])


def test_voter_measures_divide_registration_by_land_and_units(voters):
    con = voters
    reg = _registered(con, "COLUMBUS 01-B")
    # counts and density rest on the voters themselves; per housing unit on the 5 parcels
    assert _stat(con, "precinct", "COLUMBUS 01-B", "registered_voters") == (reg, round(reg))
    per_unit, parcels = _stat(con, "precinct", "COLUMBUS 01-B", "registered_voters_per_unit")
    assert (per_unit, parcels) == (pytest.approx(reg / 18), 5)  # 18 estimated housing units
    density = _stat(con, "precinct", "COLUMBUS 01-A", "registered_voters_per_sqmi")[0]
    assert density == pytest.approx(_registered(con, "COLUMBUS 01-A") / (CELL_SQMI / 2))
    county = con.execute(
        "SELECT sum(registered) FROM precinct_turnout WHERE party = 'ALL'"
    ).fetchone()[0]
    sums = dict(
        con.execute(
            "SELECT geography, sum(value) FROM parcel_stats WHERE metric = 'registered_voters'"
            " AND geography <> 'council_district' GROUP BY 1"
        ).fetchall()
    )
    assert sums and all(v == pytest.approx(county) for v in sums.values())  # nothing dropped
    assert con.execute("SELECT election_id FROM parcel_registration").fetchone()[0] == (
        "franklin-2025-11-04-general"
    )


def test_voter_measures_without_registration_are_removed(voters):
    con = voters
    con.execute("DELETE FROM precinct_turnout")
    assert refresh_voter_stats(con) == 0
    left = con.execute(
        "SELECT count(*) FROM parcel_stats WHERE metric LIKE 'registered_voters%'"
    ).fetchone()
    assert left == (0,)
    assert con.execute("SELECT count(*) FROM parcel_registration").fetchone() == (0,)


def test_property_api_names_the_election(voters, settings):
    from fastapi.testclient import TestClient

    from app.api.main import create_app

    c = TestClient(create_app(settings))
    prop = c.get("/api/catalog").json()["property"]
    groups = {m["metric"]: m["group"] for m in prop["metrics"]}
    assert groups["registered_voters_per_unit"] == "Registered voters"
    assert any("Election used: November 4, 2025 general" in n for n in prop["notes"])
    r = c.get(
        "/api/property", params={"metric": "registered_voters_per_sqmi", "geography": "ward"}
    ).json()
    assert r["kind"] == "density" and "November 4, 2025 general" in r["description"]
    assert r["universe"] == "registered voters"
    per_unit = c.get(
        "/api/property", params={"metric": "registered_voters_per_unit", "geography": "ward"}
    ).json()
    assert per_unit["universe"] is None  # residential parcels, the client's default
    assert all("rental" not in n.lower() for n in r["notes"])
