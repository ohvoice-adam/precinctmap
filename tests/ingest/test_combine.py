"""Reviewed combined contests (ingest/combine.py), on the 2020-layout fixture."""

import re

import pytest

from precinctmap.ingest import combine as combine_mod
from precinctmap.ingest.checks import long_format_check
from precinctmap.ingest.combine import Combination, combine, combined_sheet
from precinctmap.ingest.detect import parse_file
from precinctmap.ingest.errors import IngestError
from tests.fixtures.classic import ClassicSheet

E = "franklin-2020-04-28-primary"
CENTRAL = Combination(
    E,
    "Dem",
    re.compile(r"Member of County Central Committee \(.+\)"),  # COLUMBUS 01-* and BLENDON-A
    2,
    "Member of County Central Committee (all areas)",
    "test",
)


@pytest.fixture
def parsed(tmp_path):
    return parse_file(ClassicSheet().write(tmp_path / "2020-Primary-Official-Results.xlsx"))


def test_adds_one_contest_summing_its_members(parsed, monkeypatch):
    monkeypatch.setattr(combine_mod, "COMBINATIONS", (CENTRAL,))
    out = combine(parsed, E)
    assert len(out.contests) == len(parsed.contests) + 1  # members are kept
    c = out.contests[-1]
    assert (c.name_display, c.party) == ("Member of County Central Committee (all areas)", "Dem")
    assert [ch.name_display for ch in c.choices] == [
        "Carol Cruz",
        "OVER VOTES",
        "UNDER VOTES",
        "Dan Diaz",
    ]
    assert {ch.sheet for ch in c.choices} == {combined_sheet(c.ordinal)}
    votes = {
        (r.precinct_name, c.choices[r.choice_ordinal].name_display): r.votes
        for r in out.results
        if r.contest_ordinal == c.ordinal
    }
    assert (
        votes[("COLUMBUS 01-A", "Carol Cruz")] == 12 and votes[("COLUMBUS 01-A", "Dan Diaz")] == 0
    )
    assert votes[("BLENDON-A", "Dan Diaz")] == 8 and votes[("BLENDON-A", "UNDER VOTES")] == 2
    assert all(x.ok for x in out.column_checks) and long_format_check(out).failures == []
    assert any(e.kind == "combined_contest" for e in out.normalizations.entries)


def test_wrong_member_count_fails_loudly(parsed, monkeypatch):
    monkeypatch.setattr(
        combine_mod, "COMBINATIONS", (Combination(**{**CENTRAL.__dict__, "expected": 3}),)
    )
    with pytest.raises(IngestError, match="expected 3 member contests"):
        combine(parsed, E)


def test_other_elections_are_untouched(parsed, monkeypatch):
    monkeypatch.setattr(combine_mod, "COMBINATIONS", (CENTRAL,))
    assert combine(parsed, "franklin-2024-03-19-primary") is parsed


def test_the_reviewed_2020_entries_target_each_partys_three_district_contests():
    entries = {c.party: c for c in combine_mod.COMBINATIONS if c.election_id == E}
    assert set(entries) == {"Dem", "Rep"}
    rep = [
        "District Delegates and District Alternates to the National Convention"
        f" {d} Congressional District"
        for d in ("3rd", "12th", "15th")
    ]
    assert all(entries["Rep"].members.fullmatch(n) for n in rep) and entries["Rep"].expected == 3
    entry = entries["Dem"]
    names = [
        "Delegates-at-Large and Alternates-at-Large to the National Convention"
        f" {d} Congressional District"
        for d in ("3rd", "12th", "15th")
    ]
    assert all(entry.members.fullmatch(n) for n in names) and entry.expected == 3
    assert not entry.members.fullmatch(
        "Delegates-at-Large and Alternates-at-Large to the National Convention"
    )


def test_two_combinations_in_one_file_keep_their_checks_apart(parsed, monkeypatch):
    """Regression: combined choices were all keyed '(combined)' + position, so a second
    combined contest's checks overwrote the first's and blocked the review."""
    congress = Combination(
        E,
        "Dem",
        re.compile(r"Representative to Congress 3rd District"),
        1,
        "Congress (copy)",
        "test",
    )
    monkeypatch.setattr(combine_mod, "COMBINATIONS", (CENTRAL, congress))
    out = combine(parsed, E)
    assert len({ch.sheet for c in out.contests[-2:] for ch in c.choices}) == 2
    assert all(x.ok for x in out.column_checks) and long_format_check(out).failures == []
