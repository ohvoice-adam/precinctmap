"""Parcels in Ohio House/Senate districts: placed at load, backfilled for older stores."""

from precinctmap.parcels.backfill import backfill_districts
from precinctmap.serve.labels import PARCEL_DISTRICT_NOTE
from tests.parcels.test_parcels import _row, loaded  # noqa: F401  (fixture)

# House 001 = x 0-2500, 002 = x 2500-5000; Senate 003 = x 0-3000, 004 = x 3000-5000.
EXPECTED = {
    "010-000001": ("001", "003", "point_in_polygon"),  # x 500
    "010-000002": ("001", "003", "point_in_polygon"),  # x 1600
    "010-000011": ("001", "003", "point_in_polygon"),  # x 2100
    "010-000004": ("002", "004", "nearest"),  # x 5010, 10 ft outside every district
    "010-000008": ("001", "003", "nearest"),  # x -10
}


def test_parcels_are_placed_in_house_and_senate_districts(loaded):  # noqa: F811
    con, _ = loaded
    for pid, (house, senate, method) in EXPECTED.items():
        row = _row(con, pid)
        assert (row["state_house"], row["state_senate"]) == (house, senate), pid
        assert row["state_house_method"] == row["state_senate_method"] == method, pid
        assert row["state_house_set_id"] == "state-house"
        assert row["state_senate_set_id"] == "state-senate"


def _wipe_districts(con):
    con.execute(
        "UPDATE parcel_assignments SET state_house_set_id = NULL, state_house = NULL,"
        " state_house_method = NULL, state_senate_set_id = NULL, state_senate = NULL,"
        " state_senate_method = NULL"
    )
    con.execute("DELETE FROM parcel_stats WHERE geography IN ('state_house', 'state_senate')")


def _snapshot(con):
    return con.execute(
        "SELECT pid, state_house, state_house_method, state_senate, state_senate_method"
        " FROM parcel_assignments ORDER BY pid"
    ).fetchall()


def test_backfill_restores_districts_without_the_source_file(loaded):  # noqa: F811
    con, _ = loaded
    before = _snapshot(con)
    stats_before = con.execute(
        "SELECT geography, feature_id, metric, value, n FROM parcel_stats"
        " WHERE geography LIKE 'state_%' ORDER BY ALL"
    ).fetchall()
    assert before and stats_before
    _wipe_districts(con)
    assert all(r[1] is None for r in _snapshot(con))

    (result,) = backfill_districts(con, "Franklin")
    assert result.parcels == 11
    assert result.placed == {"state_house": 11, "state_senate": 11}
    assert _snapshot(con) == before
    stats_after = con.execute(
        "SELECT geography, feature_id, metric, value, n FROM parcel_stats"
        " WHERE geography LIKE 'state_%' ORDER BY ALL"
    ).fetchall()
    assert stats_after == stats_before

    backfill_districts(con, "Franklin")  # rerun is safe
    assert _snapshot(con) == before


def test_district_statistics_split_parcels_by_district(loaded):  # noqa: F811
    con, _ = loaded
    stat = lambda geo, fid: con.execute(  # noqa: E731
        "SELECT value FROM parcel_stats WHERE geography = ? AND feature_id = ?"
        " AND metric = 'residential_parcels'",
        [geo, fid],
    ).fetchone()
    # x < 2500: parcels 1,2,5,6,7,8,9,10,11 (9); x >= 2500: 3 (x 2500 -> nearest) and 4
    assert stat("state_house", "001")[0] + stat("state_house", "002")[0] == 11
    assert stat("state_senate", "003")[0] + stat("state_senate", "004")[0] == 11
    assert stat("state_senate", "004")[0] == 1  # only the x 5010 parcel


def test_backfill_with_no_district_set_logs_and_leaves_parcels_unplaced(loaded):  # noqa: F811
    con, _ = loaded
    con.execute("DELETE FROM boundary_sets WHERE geography = 'state_house'")
    _wipe_districts(con)
    (result,) = backfill_districts(con, "Franklin")
    assert result.placed["state_house"] == 0
    assert con.execute(
        "SELECT count(*) FROM parcel_log WHERE issue = 'no_state_house_set'"
    ).fetchone() == (1,)


def test_property_api_serves_districts_with_the_franklin_portion_note(loaded, settings):  # noqa: F811
    from fastapi.testclient import TestClient

    from app.api.main import create_app

    c = TestClient(create_app(settings))
    geos = [g["geography"] for g in c.get("/api/catalog").json()["property"]["geographies"]]
    assert geos[-2:] == ["state_house", "state_senate"]
    r = c.get(
        "/api/property", params={"metric": "residential_parcels", "geography": "state_senate"}
    ).json()
    assert PARCEL_DISTRICT_NOTE in r["notes"]
    assert r["features"]["004"]["value"] == 1.0
    assert sum(f["value"] for f in r["features"].values()) == 11.0  # every parcel counted once
