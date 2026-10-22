"""Turnout endpoints on the mini-county, from a primary with party ballots (2020 layout)."""

import csv
import io
from datetime import date

import pytest
from fastapi.testclient import TestClient

from app.api.main import create_app
from precinctmap.aggregate.run import aggregate
from precinctmap.ingest.commit import commit_staging
from precinctmap.ingest.staging import stage_file
from precinctmap.serve.geo import clear_cache
from tests.fixtures.classic import ClassicSheet

E = "franklin-2024-03-19-primary"  # the fixture file, dated onto a primary the registry covers


@pytest.fixture
def client(registry, settings, tmp_path):
    con, _, _ = registry
    path = ClassicSheet().write(tmp_path / "Primary-Official-Results.xlsx")
    staged = stage_file(con, settings, path, override_date=date(2024, 3, 19))
    commit_staging(con, settings, staged.staging_id)
    aggregate(con)
    clear_cache()
    return TestClient(create_app(settings))


def test_turnout_leads_the_contest_list_with_one_choice_per_party_ballot(client):
    election = next(
        e for e in client.get("/api/catalog").json()["elections"] if e["election_id"] == E
    )
    first = election["contests"][0]
    assert (first["contest_id"], first["type"], first["name"]) == (
        f"{E}:turnout",
        "turnout",
        "Turnout",
    )
    assert [c["party"] for c in first["choices"]] == ["Dem", "Rep", "Lib", "Non"]


def test_turnout_by_area_matches_the_file(client):
    r = client.get("/api/turnout", params={"election": E, "geography": "precinct"}).json()
    f = r["features"]["BLENDON-A"]
    assert (f["reg"], f["bal"], f["method"]) == (100, 90, "exact")
    assert f["v"] == [60, 25, 0, 5]  # Dem, Rep, Lib, Non ballots in choices order
    assert r["notes"][0].startswith("Turnout is ballots cast divided by registered voters")
    council = client.get("/api/turnout", params={"election": E, "geography": "council_district"})
    assert any("ballots are not shown" in n for n in council.json()["notes"])  # BLENDON is outside


def test_detail_gives_both_party_percentages(client):
    d = client.get(
        "/api/turnout/detail",
        params={"election": E, "geography": "precinct", "feature": "BLENDON-A"},
    ).json()
    assert d["turnout"] == 0.9
    dem = next(p for p in d["parties"] if p["party"] == "Dem")
    assert (dem["ballots"], dem["of_registered"], dem["of_ballots"]) == (60, 0.6, 0.6667)


def test_export_has_a_row_per_area_and_party_columns(client):
    text = client.get(
        "/api/turnout/export.csv", params={"election": E, "geography": "precinct"}
    ).text
    rows = list(csv.DictReader(io.StringIO(text)))
    assert {r["feature_id"] for r in rows} >= {"COLUMBUS 01-A", "COLUMBUS 01-B", "BLENDON-A"}
    blendon = next(r for r in rows if r["feature_id"] == "BLENDON-A")
    assert (blendon["turnout"], blendon["rep_ballots"], blendon["rep_pct_of_ballots"]) == (
        "0.9",
        "25.0",
        "0.2778",
    )
