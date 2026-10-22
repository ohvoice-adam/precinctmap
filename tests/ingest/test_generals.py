"""fcboe_general_2016 and fcboe_general_2020 (fixtures: tests/fixtures/generals.py)."""

from datetime import date

import pytest

from precinctmap.ingest.checks import long_format_check
from precinctmap.ingest.detect import parse_file
from precinctmap.ingest.errors import LayoutError
from precinctmap.ingest.identify import identify
from tests.fixtures.generals import General2016, General2020

F2016 = "2016-General-Official-Results-with-Overlaps-and-Precinct-Detail.xlsx"
F2020 = "2020-General-Election.xlsx"


def _votes(p, contest):
    c = next(x for x in p.contests if x.name_display == contest)
    return {
        (r.precinct_name, c.choices[r.choice_ordinal].name_display): r.votes
        for r in p.results
        if r.contest_ordinal == c.ordinal
    }


def test_2016_general_sums_splits_keeps_other_counties_and_reconciles(tmp_path):
    p = parse_file(General2016().write(tmp_path / F2016))
    assert p.adapter == "fcboe_general_2016"
    assert [(x.code_raw, x.name) for x in p.precincts] == [
        ("01001A", "COLUMBUS 01-A"),
        ("01001B", "COLUMBUS 01-B"),
        ("03000A", "BLENDON-A"),
    ]
    assert _votes(p, "President and Vice President")[("COLUMBUS 01-B", "Hillary Clinton")] == 36
    pres = p.contests[0]
    assert [(ch.name_display, ch.party) for ch in pres.choices] == [
        ("Hillary Clinton", "Dem"),
        ("Donald J. Trump", "Rep"),
        ("Write In", None),
    ]
    assert pres.party is None and pres.choices[2].kind == "write_in"
    levy = _votes(p, "#1 Joint Library Levy")
    assert set(levy) == {
        ("COLUMBUS 01-A", c) for c in ("For the Tax Levy", "Against the Tax Levy")
    } | {
        ("BLENDON-A", c) for c in ("For the Tax Levy", "Against the Tax Levy")
    }  # all zeros in COLUMBUS 01-B: off its ballot
    assert (
        p.out_of_county_names == ["Delaware County"]
        and sum(o.votes for o in p.out_of_county) == 100
    )
    t = {x.precinct_name: x for x in p.turnout}
    assert (t["COLUMBUS 01-B"].registered, t["COLUMBUS 01-B"].ballots_cast) == (100, 60)
    assert all(c.ok for c in p.column_checks) and long_format_check(p).failures == []
    ident = identify(F2016, p)
    assert ident.election_id == "franklin-2016-11-08-general" and ident.certified


@pytest.mark.parametrize(
    ("wb", "message"),
    [
        (General2016(bad_subtotal=True), "doesn't match its rows"),
        (General2016(stray_label="GRAND TOTAL"), "out-of-county row has unexpected name"),
    ],
)
def test_2016_general_malformed_fails_loudly(tmp_path, wb, message):
    with pytest.raises(LayoutError, match=message):
        parse_file(wb.write(tmp_path / F2016))


def test_2020_general_parses_parties_from_labels_and_completes_a_short_name(tmp_path):
    p = parse_file(General2020().write(tmp_path / F2020))
    assert p.adapter == "fcboe_general_2020"
    assert [c.name_display for c in p.contests] == [
        "President and Vice President",
        "State Board of Education 6th",
    ]
    assert [(ch.name_display, ch.party) for ch in p.contests[0].choices[:2]] == [
        ("Joseph R. Biden", "Dem"),
        ("Donald J. Trump", "Rep"),
    ]
    assert _votes(p, "State Board of Education 6th")[("COLUMBUS 01-B", "Alice Nicks")] == 20
    assert not [k for k in _votes(p, "State Board of Education 6th") if k[0] == "BLENDON-A"]
    assert [e.kind for e in p.normalizations.entries] == ["contest_name_completed"]
    t = {x.precinct_name: x for x in p.turnout}
    assert (t["BLENDON-A"].registered, t["BLENDON-A"].ballots_cast) == (60, 30)
    assert all(c.ok for c in p.column_checks) and long_format_check(p).failures == []
    ident = identify(F2020, p)
    assert ident.election_date == date(2020, 11, 3) and ident.certified is False  # no 'Official'


@pytest.mark.parametrize(
    ("wb", "message"),
    [
        (General2020(bad_part=True), "TOTAL is not Absentee"),
        (General2020(filtered_differs=True), "TOTALS and FILTERED TOTALS differ"),
        (
            General2020(
                races=[
                    ("President and Vice President", "Dem A", [1, 1, 1]),
                    ("Governor", "OVER VOTES", [0, 0, 0]),
                    ("", "UNDER VOTES", [0, 0, 0]),
                ]
            ),
            "changes name to 'Governor'",
        ),
    ],
)
def test_2020_general_malformed_fails_loudly(tmp_path, wb, message):
    with pytest.raises(LayoutError, match=message):
        parse_file(wb.write(tmp_path / F2020))
