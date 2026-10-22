"""fcboe_sheets_2016: the multi-sheet 2016 export (fixture: tests/fixtures/sheets2016.py)."""

from datetime import date

import pytest

from precinctmap.ingest.checks import long_format_check
from precinctmap.ingest.detect import WORKBOOK_ADAPTERS, parse_file
from precinctmap.ingest.errors import LayoutError
from precinctmap.ingest.identify import identify
from precinctmap.io.xlsx import read_workbook
from tests.fixtures.sheets2016 import Workbook2016

FILE = "2016-Official-Primary-Results-Precinct-Level.xlsx"


def _parse(tmp_path, wb=None):
    return parse_file((wb or Workbook2016()).write(tmp_path / FILE))


def test_claimed_by_the_workbook_adapter_and_splits_summed_into_precincts(tmp_path):
    sheets = read_workbook(Workbook2016().write(tmp_path / FILE))
    assert [a.name for a in WORKBOOK_ADAPTERS if a.detect(sheets)] == ["fcboe_sheets_2016"]
    p = _parse(tmp_path)
    assert [(x.code_raw, x.name) for x in p.precincts] == [
        ("01001A", "COLUMBUS 01-A"),
        ("01001B", "COLUMBUS 01-B"),  # two splits
        ("03000A", "BLENDON-A"),
    ]
    senate = next(c for c in p.contests if c.party == "Dem" and "Senator" in c.name_display)
    votes = {
        (r.precinct_name, senate.choices[r.choice_ordinal].name_display): r.votes
        for r in p.results
        if r.contest_ordinal == senate.ordinal
    }
    assert votes[("COLUMBUS 01-B", "Ted Strickland")] == 10 + 2  # split 1 + split 2
    assert all(c.ok for c in p.column_checks) and long_format_check(p).failures == []


def test_parties_sheets_turnout_and_placeholders(tmp_path):
    p = _parse(tmp_path)
    assert [(c.name_display, c.party) for c in p.contests] == [
        ("United States Senator", "Dem"),
        ("Chief Justice of the Supreme Court", "Dem"),
        ("United States Senator", "Rep"),
        ("United States Senator", "Grn"),
        ("#1 Grandview Heights Tax Levy", None),
    ]
    assert {ch.sheet for c in p.contests for ch in c.choices} == {
        "Democratic",
        "Republican",
        "Green",
        "Questions & Issues",
    }
    assert p.contests[1].choices[0].kind == "no_petition"  # NO CANDIDATE FILED
    assert p.contests[3].choices[0].kind == "write_in"  # WRITE IN
    t = {(row.precinct_name, row.party): row for row in p.turnout}
    assert (t[("COLUMBUS 01-B", "ALL")].registered, t[("COLUMBUS 01-B", "ALL")].ballots_cast) == (
        90,
        44,
    )
    assert (
        t[("COLUMBUS 01-B", "Dem")].ballots_cast == 23
        and t[("COLUMBUS 01-A", "Grn")].ballots_cast == 1
    )
    # all-zero contests are off the ballot: the placeholder race and the levy outside Grandview
    assert not [r for r in p.results if r.contest_ordinal == 1]
    levy = {r.precinct_name for r in p.results if r.contest_ordinal == 4}
    assert levy == {"COLUMBUS 01-A", "BLENDON-A"}


@pytest.mark.parametrize(
    ("wb", "message"),
    [
        (Workbook2016(bad_turnout_sheet="Republican"), "disagree on precincts or turnout"),
        (Workbook2016(stray_trailer=True), "unexpected row after the precincts"),
        (Workbook2016(unmerged_choice=True), "is in no contest"),
    ],
)
def test_malformed_workbooks_fail_loudly(tmp_path, wb, message):
    with pytest.raises(LayoutError, match=message):
        _parse(tmp_path, wb)


def test_identifies_the_march_2016_primary(tmp_path):
    ident = identify(FILE, _parse(tmp_path))
    assert ident.problems == [] and ident.election_date == date(2016, 3, 15)
