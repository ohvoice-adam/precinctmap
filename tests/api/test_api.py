"""API against a small seeded DuckDB (the mini-county in tests/fixtures/geo.py)."""

import csv
import io

import pytest
from fastapi.testclient import TestClient

from app.api.main import create_app
from precinctmap.serve.geo import clear_cache
from tests.fixtures.builders import Col, Sheet

E = "franklin-2025-11-04-general"
DATE = "2025-11-04"


PASSWORD = "test-admin-password-123"
ADMIN = {"auth": ("admin", PASSWORD), "headers": {"X-PRECINCTMAP-Admin": "1"}}


@pytest.fixture
def client(seeded, monkeypatch):
    monkeypatch.setenv("PRECINCTMAP_ADMIN_USER", "admin")
    monkeypatch.setenv("PRECINCTMAP_ADMIN_PASSWORD", PASSWORD)
    clear_cache()
    return TestClient(create_app(seeded))


def _contest(client, prefix):
    cat = client.get("/api/catalog").json()
    election = next(e for e in cat["elections"] if e["election_id"] == E)
    return next(c for c in election["contests"] if c["name"].startswith(prefix))


def test_catalog_lists_only_options_with_data(client):
    cat = client.get("/api/catalog").json()
    assert cat["years"] == [2025]
    (election,) = cat["elections"]
    assert election["certified"] is True
    assert election["source_file"] == "2025-General-Election_EXPORT_Official.xlsx"
    assert [g["geography"] for g in election["geographies"]] == [
        "precinct",
        "council_district",
        "municipality",
    ]  # no ZCTA set in the mini-county, so not offered
    levy = next(c for c in election["contests"] if c["type"] == "issue")
    assert [c["kind"] for c in levy["choices"]] == ["yes", "no", "over", "under"]


def test_geo_is_keyed_by_feature_id_and_cacheable(client):
    r = client.get("/api/geo/council_district", params={"date": DATE})
    assert r.status_code == 200 and r.headers["content-type"] == "application/geo+json"
    body = r.json()
    assert sorted(f["properties"]["feature_id"] for f in body["features"]) == ["1", "2"]
    assert body["retroactive"] is False
    again = client.get(
        "/api/geo/council_district",
        params={"date": DATE},
        headers={"If-None-Match": r.headers["etag"]},
    )
    assert again.status_code == 304


def test_geo_errors(client):
    assert client.get("/api/geo/states", params={"date": DATE}).status_code == 404
    old = client.get("/api/geo/precinct", params={"date": "2019-11-05"})
    assert old.status_code == 404 and "no precinct boundaries" in old.json()["detail"]
    assert client.get("/api/geo/precinct", params={"date": "not-a-date"}).status_code == 422


def test_results_council_split_and_exclusion_note(client):
    levy = _contest(client, "#1 Proposed Tax Levy")
    r = client.get(
        "/api/results",
        params={"election": E, "contest": levy["contest_id"], "geography": "council_district"},
    ).json()
    assert [c["counts"] for c in r["choices"]] == [True, True, False, False]
    assert r["features"]["2"]["v"][0] == pytest.approx(35, rel=1e-3)  # 0.7 x 50
    assert r["features"]["2"]["method"] == "allocated"
    assert r["totals"]["excluded"] == 70 + 15  # yes + no in the three non-Columbus precincts
    assert any("not part of any council district" in n for n in r["notes"])


def test_results_distinguish_not_on_ballot_from_no_data(client):
    council = _contest(client, "For Member of Council")
    r = client.get(
        "/api/results",
        params={"election": E, "contest": council["contest_id"], "geography": "precinct"},
    ).json()
    assert r["features"]["COLUMBUS 01-A"]["v"] == [30, 0, 1]
    blendon = r["features"]["BLENDON-A"]
    assert blendon["v"] is None and blendon["bal"] == 45  # not on ballot, but ballots were cast


def test_detail_has_shares_method_contributions_and_source(client):
    levy = _contest(client, "#1 Proposed Tax Levy")
    d = client.get(
        "/api/results/detail",
        params={
            "election": E,
            "contest": levy["contest_id"],
            "geography": "council_district",
            "feature": "2",
        },
    ).json()
    shares = [c["share"] for c in d["choices"] if c["counts"]]
    assert sum(shares) == pytest.approx(1.0, abs=1e-3)
    assert d["method"] == "allocated"
    (contrib,) = d["contributions"]
    assert contrib["precinct"] == "COLUMBUS 01-B" and contrib["split_share"] == pytest.approx(
        0.7, rel=1e-3
    )
    assert contrib["precinct_valid_votes"] == 55
    assert d["source_file"] == "2025-General-Election_EXPORT_Official.xlsx"


def test_exports_match_results(client):
    levy = _contest(client, "#1 Proposed Tax Levy")
    q = {"election": E, "contest": levy["contest_id"], "geography": "municipality"}
    r = client.get("/api/export.csv", params=q)
    assert r.headers["content-disposition"].endswith('_municipality.csv"')
    rows = list(csv.DictReader(io.StringIO(r.text)))
    columbus_yes = next(
        x for x in rows if x["feature_id"] == "columbus" and x["choice"] == "For the Tax Levy"
    )
    assert float(columbus_yes["votes"]) == 150 and columbus_yes["method"] == "exact"
    gj = client.get("/api/export.geojson", params=q).json()
    brice = next(f for f in gj["features"] if f["properties"]["feature_id"] == "brice")
    assert brice["properties"]["For the Tax Levy"] == pytest.approx(4, rel=1e-3)
    assert gj["source_file"] == "2025-General-Election_EXPORT_Official.xlsx"


def test_admin_upload_review_commit(client, tmp_path):
    names = [
        ("0001", "COLUMBUS 01-A"),
        ("0002", "COLUMBUS 01-B"),
        ("0003", "BLENDON-A"),
        ("0004", "HAMILTON-A"),
        ("0005", "OBETZ-D"),
    ]
    issue = "Proposed Tax Levy - Library"
    sheet = Sheet(
        names,
        [
            Col("REGISTERED VOTERS TOTAL", "", "VOTERS", [200, 100, 80, 20, 40]),
            Col("BALLOTS CAST TOTAL", "", "BALLOTS CAST", [10, 10, 10, 10, 10]),
            Col(issue, "Non", "Yes", [6, 6, 6, 6, 6]),
            Col(issue, "Non", "No", [4, 4, 4, 4, 4]),
            Col(issue, "Non", "OVER VOTES", [0] * 5),
            Col(issue, "Non", "UNDER VOTES", [0] * 5),
        ],
    )
    path = sheet.write(tmp_path / "Results.xlsx")  # no year in the name
    with path.open("rb") as f:
        staged = client.post(
            "/api/ingest",
            files={"file": ("Results.xlsx", f)},
            data={"election_date": "2026-05-05"},
            **ADMIN,
        ).json()
    assert staged["status"] == "blocked"  # content is general-like but 2026-05-05 is a primary
    with path.open("rb") as f:
        staged = client.post(
            "/api/ingest",
            files={"file": ("Results.xlsx", f)},
            data={"election_date": "2026-11-03"},
            **ADMIN,
        ).json()
    assert staged["status"] == "ready" and "Precinct match" in staged["report_text"]
    assert (
        client.get(f"/api/ingest/{staged['staging_id']}", auth=ADMIN["auth"]).json()["status"]
        == "ready"
    )
    done = client.post(f"/api/ingest/{staged['staging_id']}/commit", **ADMIN).json()
    assert done["action"] == "commit" and done["election_id"] == "franklin-2026-11-03-general"
    assert {r["geography"] for r in done["reconciliation"]} == {
        "precinct",
        "council_district",
        "municipality",
    }
    assert all(r["failures"] == 0 for r in done["reconciliation"])
    assert len(client.get("/api/catalog").json()["elections"]) == 2


def test_admin_rejects_non_xlsx_and_unknown_batches(client):
    r = client.post("/api/ingest", files={"file": ("notes.txt", b"hello")}, **ADMIN)
    assert r.status_code == 422 and "only .xlsx" in r.json()["detail"]
    assert client.get("/api/ingest/stg-000000000000", auth=ADMIN["auth"]).status_code == 422
    assert client.post("/api/ingest/stg-000000000000/commit", **ADMIN).status_code == 422


def test_map_is_public_but_admin_needs_login(client):
    assert client.get("/api/catalog").status_code == 200  # no credentials needed
    r = client.post("/api/ingest/stg-000000000000/commit")
    assert r.status_code == 401 and r.headers["www-authenticate"].startswith("Basic")
    wrong = client.post("/api/ingest/stg-000000000000/commit", auth=("admin", "nope"))
    assert wrong.status_code == 401


def test_admin_posts_need_the_csrf_header(client):
    r = client.post("/api/ingest/stg-000000000000/commit", auth=ADMIN["auth"])
    assert r.status_code == 403 and "X-PRECINCTMAP-Admin" in r.json()["detail"]


def test_admin_fails_closed_without_a_real_password(client, monkeypatch):
    monkeypatch.setenv("PRECINCTMAP_ADMIN_PASSWORD", "changeme")
    r = client.get("/api/ingest/stg-000000000000", auth=("admin", "changeme"))
    assert r.status_code == 503 and "not configured" in r.json()["detail"]


def test_admin_page_is_behind_login(seeded, monkeypatch, tmp_path):
    from dataclasses import replace

    monkeypatch.setenv("PRECINCTMAP_ADMIN_PASSWORD", PASSWORD)
    web = tmp_path / "web"
    web.mkdir()
    (web / "index.html").write_text("<title>map</title>")
    (web / "admin.html").write_text("<title>admin</title>")
    c = TestClient(create_app(replace(seeded, static_dir=web)))
    assert c.get("/").status_code == 200
    assert c.get("/admin").status_code == 401
    assert c.get("/admin.html").status_code == 401  # static mount must not bypass the login
    page = c.get("/admin", auth=ADMIN["auth"])
    assert page.status_code == 200 and "<title>admin</title>" in page.text


def test_council_districts_before_2023_are_labeled_retroactive():
    from precinctmap.serve.geo import _notes
    from precinctmap.serve.labels import RETROACTIVE_COUNCIL

    assert RETROACTIVE_COUNCIL in _notes("council_district", retroactive=True)
    assert RETROACTIVE_COUNCIL not in _notes("council_district", retroactive=False)
