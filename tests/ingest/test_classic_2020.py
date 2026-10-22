"""fcboe_classic_2020: the 2020-layout FCBOE export (fixture: tests/fixtures/classic.py)."""

from datetime import date

import pytest

from precinctmap.ingest.detect import ADAPTERS, detect_adapter
from precinctmap.ingest.errors import LayoutError
from precinctmap.ingest.identify import identify
from precinctmap.io.xlsx import read_single_sheet
from tests.fixtures.builders import sheet_2024, sheet_2025
from tests.fixtures.classic import ClassicSheet


def _grid(tmp_path, sheet=None):
    return read_single_sheet(
        (sheet or ClassicSheet()).write(tmp_path / "2020-Primary-Official-Results.xlsx")
    )


def _parse(tmp_path, sheet=None):
    grid = _grid(tmp_path, sheet)
    return detect_adapter(grid, "f.xlsx").parse(grid)


def test_only_the_classic_adapter_claims_it_and_it_claims_nothing_else(tmp_path):
    grid = _grid(tmp_path)
    assert [a.name for a in ADAPTERS if a.detect(grid)] == ["fcboe_classic_2020"]
    classic = next(a for a in ADAPTERS if a.name == "fcboe_classic_2020")
    for other in (sheet_2024(), sheet_2025()):
        assert not classic.detect(read_single_sheet(other.write(tmp_path / "o.xlsx")))


def test_same_name_contests_split_by_party_and_reconcile(tmp_path):
    p = _parse(tmp_path)
    congress = [(c.name_display, c.party) for c in p.contests if "Congress" in c.name_display]
    assert congress == [("Representative to Congress 3rd District", "Dem"),
                        ("Representative to Congress 3rd District", "Rep")]  # fmt: skip
    assert (
        all(c.ok for c in p.column_checks) and len(p.column_checks) == 11 + 19
    )  # 5 registered + 6 ballot totals, 19 choices
    assert p.has_over_under and p.county == "Franklin"
    by_name = {(c.name_display, c.party): c for c in p.contests}
    levy = by_name[("Joint Library Levy", None)]
    assert levy.contest_type == "issue" and [ch.kind for ch in levy.choices] == [
        "yes",
        "no",
        "over",
        "under",
    ]


def test_repeated_names_get_the_area_from_the_file_and_write_ins_are_named(tmp_path):
    p = _parse(tmp_path)
    names = [c.name_display for c in p.contests if "Central" in c.name_display]
    assert names == [
        "Member of County Central Committee (COLUMBUS 01-*)",  # both COLUMBUS 01 precincts
        "Member of County Central Committee (BLENDON-A)",
        "Member of County Central Committee, write-in",
    ]
    kinds = {e.kind for e in p.normalizations.entries}
    assert {"repeated_contest_name", "write_in_contest_name", "ward_number"} <= kinds


def test_precinct_codes_turnout_and_other_counties(tmp_path):
    p = _parse(tmp_path)
    assert [(x.code_raw, x.name) for x in p.precincts] == [
        ("01001A", "COLUMBUS 01-A"),
        ("01001B", "COLUMBUS 01-B"),
        ("03000A", "BLENDON-A"),  # ward-less township precinct: ward '00'
    ]
    t = {(row.precinct_name, row.party): row for row in p.turnout}
    assert (t[("BLENDON-A", "ALL")].registered, t[("BLENDON-A", "ALL")].ballots_cast) == (100, 90)
    assert t[("BLENDON-A", "Dem")].ballots_cast == 60 and t[("BLENDON-A", "ALL")].ballots_blank == 1
    assert p.out_of_county_names == ["Delaware County"]
    assert sum(o.votes for o in p.out_of_county) == 70 + 60 + 5
    # a contest is off a precinct's ballot only when every column, under-votes included, is 0
    carol = [r for r in p.results if r.precinct_name == "BLENDON-A" and r.contest_ordinal == 2]
    assert carol == []


@pytest.mark.parametrize(
    ("sheet", "message"),
    [
        (ClassicSheet(break_cycle=True), "ABSENTEE"),
        (ClassicSheet(bad_part=True), "TOTAL is not ABSENTEE"),
        (ClassicSheet(filtered_differs=True), "Total Votes and Filtered Totals differ"),
    ],
)
def test_malformed_files_fail_loudly(tmp_path, sheet, message):
    with pytest.raises(LayoutError, match=message):
        _parse(tmp_path, sheet)


def test_contest_without_under_votes_is_rejected(tmp_path):
    sheet = ClassicSheet()
    last = sheet.contests[-1]
    sheet.contests[-1] = type(last)(
        last.name, last.party, last.labels[:-1], {r: v[:-1] for r, v in last.votes.items()}
    )
    with pytest.raises(LayoutError, match="no closing UNDER VOTES"):
        _parse(tmp_path, sheet)


def test_identifies_the_april_2020_primary(tmp_path):
    p = _parse(tmp_path)
    ident = identify("2020-Primary-Official-Results.xlsx", p)
    assert ident.problems == [] and ident.election_date == date(2020, 4, 28)
    assert ident.election_id == "franklin-2020-04-28-primary"
