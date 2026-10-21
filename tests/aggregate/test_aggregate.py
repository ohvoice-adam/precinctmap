"""Aggregation on the mini-county: hand-computable expected values for every geography."""

import pytest

from precinctmap.aggregate.reconcile import ReconciliationError, reconcile_election
from precinctmap.aggregate.run import aggregate
from precinctmap.ingest.commit import commit_staging
from precinctmap.ingest.staging import stage_file
from tests.fixtures.builders import mini_county_sheet

E = "franklin-2025-11-04-general"


@pytest.fixture
def aggregated(registry, settings, tmp_path):
    con, _, _ = registry
    path = mini_county_sheet().write(tmp_path / "2025-General-Election_EXPORT_Official.xlsx")
    staged = stage_file(con, settings, path)
    assert staged.report["status"] == "ready", staged.report["blockers"]
    commit_staging(con, settings, staged.staging_id)
    return con, aggregate(con, [E])


def _votes(con, geography, feature, choice_suffix):
    row = con.execute(
        "SELECT votes, method FROM geo_results WHERE election_id = ? AND geography = ?"
        " AND feature_id = ? AND choice_id LIKE ?",
        [E, geography, feature, f"%:{choice_suffix}"],
    ).fetchone()
    return (None, None) if row is None else (row[0], row[1])


def test_council_districts_split_by_population_and_exclude_non_columbus(aggregated):
    con, _ = aggregated
    d1, m1 = _votes(con, "council_district", "1", "for-the-tax-levy")
    d2, m2 = _votes(con, "council_district", "2", "for-the-tax-levy")
    assert d1 == pytest.approx(100 + 0.3 * 50, rel=1e-3) and m1 == "mixed"
    assert d2 == pytest.approx(0.7 * 50, rel=1e-3) and m2 == "allocated"
    rec = con.execute(
        "SELECT source, mapped, excluded, unassigned, ok FROM geo_reconciliation"
        " WHERE geography = 'council_district' AND choice_id LIKE '%:for-the-tax-levy'"
    ).fetchone()
    assert rec[0] == 220 and rec[2] == 40 + 10 + 20 and rec[3] == 0 and rec[4]
    assert rec[1] == pytest.approx(150)


def test_columbus_only_contest_maps_fully_onto_districts(aggregated):
    con, _ = aggregated
    rec = con.execute(
        "SELECT source, mapped, excluded FROM geo_reconciliation"
        " WHERE geography = 'council_district' AND choice_id LIKE '%:ann-lee'"
    ).fetchone()
    assert rec[0] == 50 and rec[1] == pytest.approx(50) and rec[2] == 0


def test_municipalities_exact_except_village_host(aggregated):
    con, _ = aggregated
    assert _votes(con, "municipality", "columbus", "for-the-tax-levy") == (150, "exact")
    assert _votes(con, "municipality", "obetz", "for-the-tax-levy") == (20, "exact")
    brice, method = _votes(con, "municipality", "brice", "for-the-tax-levy")
    assert brice == pytest.approx(0.1 * 40, rel=1e-3) and method == "allocated"


def test_precinct_geography_is_identity(aggregated):
    con, summaries = aggregated
    assert _votes(con, "precinct", "COLUMBUS 01-B", "for-the-tax-levy") == (50, "exact")
    assert {s.geography for s in summaries} == {
        "precinct",
        "council_district",
        "municipality",
    }  # no ZCTA set in the mini-county registry
    assert all(s.failures == 0 for s in summaries)


def test_contributions_and_turnout_carry_split_shares(aggregated):
    con, _ = aggregated
    share = con.execute(
        "SELECT split_share, method FROM geo_contributions WHERE geography = 'council_district'"
        " AND feature_id = '2' AND precinct_name = 'COLUMBUS 01-B'"
    ).fetchone()
    assert share[0] == pytest.approx(0.7, rel=1e-3) and share[1] == "allocated"
    registered = con.execute(
        "SELECT registered FROM geo_turnout WHERE geography = 'council_district'"
        " AND feature_id = '1' AND party = 'ALL'"
    ).fetchone()[0]
    assert registered == pytest.approx(200 + 0.3 * 100, rel=1e-3)


def test_reconciliation_catches_lost_votes(aggregated):
    con, _ = aggregated
    con.execute("DELETE FROM geo_results WHERE geography = 'municipality' AND feature_id = 'obetz'")
    with pytest.raises(ReconciliationError, match="municipality"):
        reconcile_election(con, E)
