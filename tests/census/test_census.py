"""ACS census layer on the mini-county: fetch, allocation, estimates, commit, API."""

from datetime import date

import numpy as np
import pandas as pd
import pytest

from precinctmap.census.estimates import line_sum, median_from_brackets, proportion, reliable
from precinctmap.census.load import commit_release, fetch_release, release_dir, review_release
from precinctmap.census.summary_file import read_table
from precinctmap.census.tables import INCOME_EDGES, INCOME_TOP
from precinctmap.ingest.errors import UnknownLayoutError
from tests.fixtures.census import BG_A, YEAR, write_national_tables

AS_OF = date(2026, 10, 21)


@pytest.fixture
def fetched(registry, settings, tmp_path):
    con, cfg, _ = registry
    root = write_national_tables(tmp_path / "census")
    files = fetch_release(settings.data_dir, YEAR, "39049", base_url=f"file://{root}")
    return con, cfg, files


@pytest.fixture
def review(fetched, settings):
    con, cfg, _ = fetched
    return review_release(con, cfg, settings.data_dir, YEAR, AS_OF)


def stat(review, geography, feature, metric):
    s = review.computed.stats
    row = s[(s.geography == geography) & (s.feature_id == feature) & (s.metric == metric)]
    assert len(row) == 1, (geography, feature, metric)
    return row.iloc[0]


def test_fetch_keeps_only_the_county(fetched, settings):
    _, _, files = fetched
    by_table = {f.table: f for f in files}
    assert by_table["B15003"].block_groups == 3 and by_table["B15003"].tracts == 0
    assert by_table["B05002"].tracts == 2 and by_table["B05002"].block_groups == 0
    text = (release_dir(settings.data_dir, YEAR) / "acsdt5y2024-b15003.dat").read_text()
    assert "390410001001" not in text and "0100000US" not in text  # other county, nation dropped
    assert text.startswith("GEO_ID|B15003_E001|B15003_M001")


def test_reader_rejects_unknown_layouts(tmp_path):
    bad = tmp_path / "x.dat"
    bad.write_text("GEO_ID|B15003_E001|B99999_M001\n1500000US390490001001|1|2\n")
    with pytest.raises(UnknownLayoutError):
        read_table(bad, "B15003")
    bad.write_text(
        "GEO_ID|B15003_E001|B15003_M001\n1500000US390490001001|N|2\n0500000US39049|1|1\n"
    )
    with pytest.raises(UnknownLayoutError, match="non-numeric"):
        read_table(bad, "B15003")
    bad.write_text(
        "GEO_ID|B15003_E001|B15003_M001\n1500000US390490001001|5|-222222222\n0500000US39049|5|1\n"
    )
    with pytest.raises(UnknownLayoutError, match="MOE code"):
        read_table(bad, "B15003")


def test_population_follows_blocks_into_every_geography(review):
    assert stat(review, "precinct", "COLUMBUS 01-A", "population").value == pytest.approx(100)
    assert stat(review, "precinct", "COLUMBUS 01-A", "population").moe == pytest.approx(10)
    assert stat(review, "precinct", "BLENDON-A", "population").value == pytest.approx(100)
    assert stat(review, "council_district", "1", "population").value == pytest.approx(130)
    assert stat(review, "council_district", "2", "population").value == pytest.approx(70)
    assert stat(review, "municipality", "brice", "population").value == pytest.approx(10)
    assert stat(review, "ward", "columbus-ward-01", "population").value == pytest.approx(200)
    s = review.computed.stats
    totals = s[s.metric == "population"].groupby("geography")["value"].sum().round(6).to_dict()
    assert totals["precinct"] == totals["municipality"] == totals["ward"] == 400
    assert totals["council_district"] == 200  # Columbus blocks only
    assert all(units == county for _, units, county in review.county_checks)


def test_share_and_its_margin_of_error(review):
    row = stat(review, "precinct", "COLUMBUS 01-A", "bachelors_share")
    # half of block group A: 30 of 60; MOE_num^2 = 0.25 * 157, MOE_den = 6 -> sqrt(30.25) / 60
    assert row.value == pytest.approx(0.5) and row.base == pytest.approx(60)
    assert row.moe == pytest.approx(5.5 / 60)
    assert row.reliable


def test_median_income_from_brackets(review):
    assert stat(
        review, "precinct", "COLUMBUS 01-A", "median_household_income"
    ).value == pytest.approx(67_500)
    assert stat(review, "precinct", "BLENDON-A", "median_household_income").value == pytest.approx(
        5_000
    )
    top = stat(review, "precinct", "HAMILTON-A", "median_household_income")
    assert top.value == INCOME_TOP  # open top bracket: reported as $200,000 (or more)
    assert stat(review, "precinct", "COLUMBUS 01-A", "median_household_income").moe > 0


def test_tract_only_table_and_reliability(review):
    row = stat(review, "precinct", "COLUMBUS 01-A", "noncitizen_share")
    assert row.value == pytest.approx(0.1)  # a third of tract 1: 10 of 100
    zero = stat(review, "precinct", "HAMILTON-A", "noncitizen_share")
    assert zero.value == 0 and zero.moe > 0 and not zero.reliable  # 0 +/- 9: not reliable


def test_density_uses_block_land_area(review):
    sq_mi = 1_000_000 * 0.09290304 / 2_589_988.110336  # block 1: 1000 x 1000 ft
    row = stat(review, "precinct", "COLUMBUS 01-A", "population_density")
    assert row.value == pytest.approx(100 / sq_mi, rel=1e-3)


def test_commit_is_idempotent_and_replaces_changed_files(fetched, review, settings):
    con, cfg, _ = fetched
    assert commit_release(con, review, cfg.county) == "committed"
    n = con.execute("SELECT count(*) FROM census_stats").fetchone()[0]
    assert n == len(review.computed.stats) and n > 0
    assert commit_release(con, review, cfg.county) == "noop"
    con.execute("DELETE FROM census_stats WHERE geography = 'ward'")  # as before wards existed
    assert commit_release(con, review, cfg.county) == "replaced"
    assert con.execute("SELECT count(*) FROM census_stats").fetchone()[0] == n
    path = release_dir(settings.data_dir, YEAR) / "acsdt5y2024-b01003.dat"
    path.write_text(path.read_text().replace(f"1500000US{BG_A}|200|20", f"1500000US{BG_A}|210|20"))
    again = review_release(con, cfg, settings.data_dir, YEAR, AS_OF)
    assert commit_release(con, again, cfg.county) == "replaced"
    issues = [r[0] for r in con.execute("SELECT issue FROM census_log").fetchall()]
    assert "replaced" in issues


def test_census_api(fetched, review, settings):
    from fastapi.testclient import TestClient

    from app.api.main import create_app

    con, cfg, _ = fetched
    commit_release(con, review, cfg.county)
    c = TestClient(create_app(settings))
    cat = c.get("/api/catalog").json()["census"]
    assert cat["dataset"] == "census" and cat["label"].startswith(
        "Census demographics (ACS 2020-2024"
    )
    assert {m["group"] for m in cat["metrics"]} >= {"Education", "Immigration", "Urbanism"}
    r = c.get("/api/census", params={"metric": "bachelors_share", "geography": "precinct"}).json()
    assert r["features"]["COLUMBUS 01-A"] == {
        "value": 0.5,
        "n": 60,
        "moe": 0.0917,
        "reliable": True,
    }
    assert r["universe"] == "adults 25 and older" and "B15003" in r["source_file"]
    d = c.get("/api/census/detail", params={"geography": "municipality", "feature": "brice"}).json()
    assert {m["metric"]: m["value"] for m in d["metrics"]}["population"] == 10
    assert "sha256" in d["source_file"]
    csv_text = c.get("/api/census/export.csv", params={"geography": "precinct"}).text
    assert csv_text.splitlines()[0].startswith(
        "geography,feature_id,feature_name,metric,label,value,moe_90"
    )
    assert (
        c.get("/api/census", params={"metric": "nope", "geography": "precinct"}).status_code == 404
    )


def test_zero_estimate_moe_counts_once():
    est = pd.DataFrame({1: [0.0], 2: [0.0], 3: [5.0]}, index=["u"])
    moe = pd.DataFrame({1: [9.0], 2: [12.0], 3: [4.0]}, index=["u"])
    v = line_sum(est, moe, (1, 2, 3)).loc["u", "V"]
    assert v == pytest.approx(12.0**2 + 4.0**2)


def test_proportion_falls_back_to_ratio_formula():
    num = pd.DataFrame({"E": [9.0], "V": [1.0]}, index=["f"])
    den = pd.DataFrame({"E": [10.0], "V": [100.0]}, index=["f"])
    out = proportion(num, den).loc["f"]
    assert out.value == pytest.approx(0.9)
    assert out.moe == pytest.approx(np.sqrt(1.0 + 0.81 * 100.0) / 10)  # radicand < 0


def test_reliability_and_empty_medians():
    assert reliable(100, 40) and not reliable(100, 60) and not reliable(None, 1)
    assert reliable(0, 0) and not reliable(0, 5)
    assert median_from_brackets(np.zeros(16), np.zeros(16), INCOME_EDGES, INCOME_TOP) == (
        None,
        None,
    )
