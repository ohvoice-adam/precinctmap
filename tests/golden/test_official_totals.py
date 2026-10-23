"""Golden: the store and every geography reproduce the BOE's certified county totals.

Values come from scripts/extract_official_totals.py, which reads the certified exports with
openpyxl and no precinctmap code. If a change moves one of these numbers, stop and explain why
before regenerating the file (CLAUDE.md, Testing).
"""

import json
from pathlib import Path

import pytest

from precinctmap.config import load_settings
from precinctmap.io.db import StoreLockedError, close_all, get_connection

GOLDEN = json.loads((Path(__file__).parent / "official_totals.json").read_text())
DB = load_settings().db_path


@pytest.fixture(scope="module")
def store():
    if not DB.exists():
        pytest.skip(f"no store at {DB}; ingest the samples to run golden tests")
    try:
        con = get_connection(DB)
    except StoreLockedError as exc:
        pytest.skip(f"store is in use by another process (stop the API to run golden tests): {exc}")
    yield con
    close_all()


def _choice_id(con, g) -> str:
    rows = con.execute(
        "SELECT h.choice_id FROM choices h JOIN contests c ON c.contest_id = h.contest_id"
        " WHERE c.election_id = ? AND c.name_raw = ? AND h.name_raw = ?",
        [g["election_id"], g["contest_raw"], g["choice_raw"]],
    ).fetchall()
    assert len(rows) == 1, f"{g['contest_raw']} / {g['choice_raw']}: {rows}"
    return str(rows[0][0])


@pytest.mark.parametrize("g", GOLDEN, ids=lambda g: f"{g['election_id']}:{g['choice_raw']}")
def test_store_reproduces_official_totals(store, g):
    choice = _choice_id(store, g)
    franklin = store.execute(
        "SELECT sum(votes) FROM precinct_results WHERE choice_id = ?", [choice]
    ).fetchone()[0]
    other = store.execute(
        "SELECT coalesce(sum(votes), 0) FROM out_of_county_results WHERE choice_id = ?", [choice]
    ).fetchone()[0]
    assert franklin == g["franklin_precincts"]
    assert other == g["other_counties"]
    assert franklin + other == g["county_total_row"]


@pytest.mark.parametrize("g", GOLDEN, ids=lambda g: f"{g['election_id']}:{g['choice_raw']}")
def test_every_geography_reproduces_franklin_total(store, g):
    choice = _choice_id(store, g)
    rows = store.execute(
        "SELECT geography, mapped, excluded, unassigned, ok FROM geo_reconciliation"
        " WHERE choice_id = ?",
        [choice],
    ).fetchall()
    assert {r[0] for r in rows} == {"precinct", "council_district", "municipality", "ward", "zcta"}
    for geography, mapped, excluded, unassigned, ok in rows:
        assert ok
        assert mapped + excluded + unassigned == pytest.approx(g["franklin_precincts"], abs=1e-6)
        assert unassigned == 0
        if geography != "council_district" or g["columbus_only"]:
            # Columbus-only contests sit entirely in Columbus precincts: nothing excluded.
            assert mapped == pytest.approx(g["franklin_precincts"], abs=1e-6), geography
