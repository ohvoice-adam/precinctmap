from datetime import date

import pytest

from precinctmap.ingest.errors import StagingError, UnknownLayoutError
from precinctmap.parcels.auditor import read_parcels
from precinctmap.parcels.ingest import commit_parcels, load_addresses, stage_parcels
from precinctmap.parcels.voterfile import read_voter_addresses
from tests.fixtures.parcels import write_parcel_csv, write_voter_file

AS_OF = date(2026, 10, 21)


@pytest.fixture
def loaded(registry, settings, tmp_path):
    con, _, _ = registry
    load_addresses(con, write_voter_file(tmp_path / "VOTERFILE.TXT"), AS_OF, commit=True)
    report = stage_parcels(con, settings, write_parcel_csv(tmp_path / "Parcel.csv"), AS_OF)
    commit_parcels(con, settings, report["staging_id"])
    return con, report


def _row(con, pid):
    cur = con.execute("SELECT * FROM parcel_assignments WHERE pid = ?", [pid])
    cols = [d[0] for d in cur.description]
    return dict(zip(cols, cur.fetchone(), strict=True))


def test_reader_repairs_broken_quotes_and_drops_owner_columns(tmp_path):
    read = read_parcels(write_parcel_csv(tmp_path / "Parcel.csv"))
    assert len(read.frame) == 11 and read.rows_read == 11
    assert [issue for _, issue, _ in read.log] == ["repaired_row"]
    assert "OWNER PERSON" not in read.frame.to_csv() and "SECRET LN" not in read.frame.to_csv()
    assert read.frame.loc[read.frame.pid == "010-000006", "street"].item() == "MAIN ST"


def test_reader_rejects_unknown_layout(tmp_path):
    bad = tmp_path / "x.csv"
    bad.write_text("PID,ADDRESS\n1,2\n")
    with pytest.raises(UnknownLayoutError):
        read_parcels(bad)


def test_voter_file_keeps_only_addresses(con, tmp_path):
    read = read_voter_addresses(con, write_voter_file(tmp_path / "VOTERFILE.TXT"))
    assert read.rows_read == 9 and len(read.frame) == 8  # two voters share 100 MAIN ST
    assert set(read.frame.columns) == {
        "zip5",
        "house_no",
        "street",
        "precinct_code",
        "precinct_codes",
        "council_district",
        "city_code",
        "units_with_voters",
    }
    assert "SECRETNAME" not in read.frame.to_csv() and "OH0000" not in read.frame.to_csv()
    assert read.frame.set_index("street").loc["OAK ST"].shape[0] == 2


def test_every_parcel_gets_a_precinct(loaded):
    con, report = loaded
    assert report["precinct"]["assigned"] == 11
    assert _row(con, "010-000001")["precinct_name"] == "COLUMBUS 01-A"
    far = _row(con, "010-000004")
    assert far["precinct_method"] == "nearest" and far["precinct_name"] == "OBETZ-D"
    assert far["precinct_distance_ft"] == pytest.approx(10, abs=0.5)


def test_council_only_for_columbus_with_fallbacks(loaded):
    con, _ = loaded
    assert _row(con, "010-000002")["council_district"] == "2"
    assert _row(con, "010-000003")["council_method"] == "not_in_columbus"
    voter = _row(con, "010-000008")
    assert (voter["council_method"], voter["council_district"]) == ("voter_address", "1")
    nearest = _row(con, "010-000009")
    assert (nearest["council_method"], nearest["council_district"]) == ("nearest", "1")


def test_voter_cross_check_ranges_and_disagreements(loaded):
    con, report = loaded
    ranged = _row(con, "010-000005")
    assert ranged["voter_precinct"] == "COLUMBUS 01-B" and ranged["precinct_agrees"]  # 403 ignored
    pine = _row(con, "010-000007")  # the voter file wins; geometry is kept for the record
    assert (pine["precinct_name"], pine["geometry_precinct"]) == ("COLUMBUS 01-B", "COLUMBUS 01-A")
    assert pine["precinct_method"] == "voter_address" and pine["precinct_agrees"] is False
    assert report["voter_check"]["precinct_disagreements"] == 2
    issues = dict(con.execute("SELECT issue, count(*) FROM parcel_log GROUP BY 1").fetchall())
    assert issues["precinct_voter_override"] == 2 and issues["repaired_row"] == 1


def test_override_across_jurisdictions_moves_municipality_and_council(loaded):
    con, _ = loaded
    elm = _row(con, "010-000011")
    assert (elm["geometry_precinct"], elm["precinct_name"]) == ("BLENDON-A", "COLUMBUS 01-B")
    assert (elm["municipality"], elm["municipality_method"]) == ("columbus", "voter_address")
    assert (elm["council_district"], elm["council_method"]) == ("2", "voter_address")


def test_apartment_units_come_from_the_census_block(loaded):
    con, _ = loaded
    apt = con.execute(
        "SELECT apartment, likely_rental, units_estimate, units_method FROM parcels"
        " WHERE pid = '010-000010'"
    ).fetchone()
    # block 2 (x 1000-1400): 15 housing units - 1 unit at 400-404 OAK ST = 14, within 4-19
    assert apt == (True, True, 14.0, "census_block")


def test_no_personal_data_reaches_the_store(loaded):
    con, _ = loaded
    dump = " ".join(
        str(v)
        for t in ("parcels", "parcel_assignments", "parcel_log", "voter_addresses")
        for row in con.execute(f"SELECT * FROM {t}").fetchall()
        for v in row
    )
    for secret in (
        "OWNER PERSON",
        "RENTCO",
        "FAR AWAY",
        "SECRET LN",
        "SECRETNAME",
        "1970",
        "OH0000",
    ):
        assert secret not in dump


def test_same_file_is_noop_and_replacement_needs_confirmation(loaded, settings, tmp_path):
    con, _ = loaded
    again = stage_parcels(con, settings, tmp_path / "Parcel.csv", AS_OF)
    assert again["status"] == "noop"
    changed = tmp_path / "v2" / "Parcel.csv"
    changed.parent.mkdir()
    write_parcel_csv(changed)
    changed.write_text(
        changed.read_text(encoding="utf-8-sig").replace("100000", "200000"), encoding="utf-8-sig"
    )
    staged = stage_parcels(con, settings, changed, AS_OF)
    with pytest.raises(StagingError, match="would replace"):
        commit_parcels(con, settings, staged["staging_id"])
    commit_parcels(con, settings, staged["staging_id"], allow_replace=True)
    assert con.execute("SELECT count(*) FROM parcels").fetchone()[0] == 11
    assert con.execute("SELECT max(appraised_total) FROM parcels").fetchone()[0] == 200000


def test_rental_flags_and_grade_scores():
    import pandas as pd

    from precinctmap.parcels.tenure import derive, grade_score

    assert [grade_score(g) for g in ("A", "C+1", "B-2", "D+2", "E", "", "X")] == [
        5.0,
        3.2,
        3.6,
        2.4,
        1.0,
        None,
        None,
    ]
    raw = pd.DataFrame(
        {
            "NAME1": ["SMITH JOHN", "ACME L.L.C.", "BILLCO INC", "DOE JANE"],
            "NAME2": ["", "", "", ""],
            "NAME3": ["", "", "", ""],
            "OWNER_ADD1": ["12 ELM ST", "1 OTHER ST", "5 OAK AVE", ""],
            "OWNER_ADD2": ["COLUMBUS OH 43215", "COLUMBUS OH 43215", "DAYTON OH 45402", ""],
            "STADDR": ["12 ELM ST", "7 ELM ST", "5 OAK AVE", "9 PINE RD"],
            "ZIPCODE": ["43215", "43215", "43215", "43215"],
            "PCLASS": ["R", "R", "R", "C"],
            "DWELTYP": ["1", "1", "1", "1"],
            "GRADE": ["C", "C", "C", "C"],
            "LANDUSE": ["510", "520", "510", "499"],
        }
    )
    d = derive(raw)
    assert d["owner_llc"].tolist() == [False, True, False, False]  # BILLCO is not an LLC
    assert d["owner_address_differs"].tolist() == [False, True, True, pd.NA]
    assert d["likely_rental"].tolist() == [False, True, True, False]
    assert d["residential"].tolist() == [True, True, True, False]
    assert d["units_estimate"].tolist()[:3] == [1.0, 2.0, 1.0]  # 520 = two-family
    apt = derive(raw.assign(LANDUSE=["510", "510", "510", "403"]))
    assert apt["apartment"].tolist() == [False, False, False, True]
    assert apt["likely_rental"].iloc[3] and apt["residential"].iloc[3]  # apartments are rentals


def test_area_statistics_and_totals(loaded):
    con, _ = loaded
    stat = lambda geo, fid, m: con.execute(  # noqa: E731
        "SELECT value, n FROM parcel_stats WHERE geography = ? AND feature_id = ? AND metric = ?",
        [geo, fid, m],
    ).fetchone()
    # 01-B: -000002, -000005, apartment -000010; -000007 and -000011 moved in by the voter file
    assert stat("precinct", "COLUMBUS 01-B", "residential_parcels") == (5, 5)
    assert stat("precinct", "COLUMBUS 01-B", "likely_rentals") == (2, 5)  # elsewhere + apartment
    assert stat("precinct", "COLUMBUS 01-B", "housing_units") == (18, 5)  # 1+1+14+1+1
    assert stat("precinct", "COLUMBUS 01-B", "likely_rental_units") == (15, 5)
    assert stat("precinct", "BLENDON-A", "llc_owned") == (1, 1)
    assert stat("council_district", "2", "likely_rental_share") == (0.5, 2)  # -000002, -000011
    assert stat("precinct", "COLUMBUS 01-A", "median_building_value") == (150_000, 4)
    mean_minus_median = stat("precinct", "COLUMBUS 01-A", "building_value_mean_minus_median")[0]
    assert mean_minus_median == pytest.approx(-12_500)  # 100k, 150k x3
    assert stat("precinct", "COLUMBUS 01-B", "median_building_value")[1] == 4  # apartment excluded
    totals = dict(
        con.execute(
            "SELECT geography, sum(value) FROM parcel_stats"
            " WHERE metric = 'residential_parcels' GROUP BY 1"
        ).fetchall()
    )
    assert totals == {"precinct": 11, "municipality": 11, "council_district": 9}


def test_property_api(loaded, settings):
    from fastapi.testclient import TestClient

    from app.api.main import create_app

    c = TestClient(create_app(settings))
    prop = c.get("/api/catalog").json()["property"]
    assert prop["as_of"] == "2026-10-21" and "likely_rental_share" in [
        m["metric"] for m in prop["metrics"]
    ]
    r = c.get("/api/property", params={"metric": "likely_rentals", "geography": "precinct"}).json()
    assert r["features"]["COLUMBUS 01-B"] == {"value": 2.0, "n": 5}
    d = c.get(
        "/api/property/detail", params={"geography": "precinct", "feature": "BLENDON-A"}
    ).json()
    assert {m["metric"]: m["value"] for m in d["metrics"]}["llc_owned"] == 1
    assert d["grades"] == [{"grade": "B", "parcels": 1}]
    csv_text = c.get("/api/property/export.csv", params={"geography": "precinct"}).text
    assert (
        "RENTCO" not in csv_text and "OWNER PERSON" not in csv_text and "likely_rentals" in csv_text
    )
    assert (
        c.get("/api/property", params={"metric": "nope", "geography": "precinct"}).status_code
        == 404
    )
