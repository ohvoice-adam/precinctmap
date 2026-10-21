from pathlib import Path

import pytest

from precinctmap.ingest.detect import detect_adapter
from precinctmap.ingest.errors import LayoutError, UnknownLayoutError
from precinctmap.io.xlsx import read_single_sheet
from tests.fixtures.builders import Col, sheet_2024, sheet_2025, sheet_2025_primary


def _parse(sheet, tmp_path: Path, name: str = "f.xlsx"):
    grid = read_single_sheet(sheet.write(tmp_path / name))
    adapter = detect_adapter(grid, name)
    return adapter, adapter.parse(grid)


# --- fcboe_wide_2025 ------------------------------------------------------------------


def test_2025_parses_contests_choices_and_parties(tmp_path):
    adapter, p = _parse(sheet_2025(), tmp_path)
    assert adapter.name == "fcboe_wide_2025"
    assert p.county == "Franklin"
    council, zoo = p.contests
    assert council.name_display == "For Member of Council City of Bexley"
    assert council.jurisdiction == "City of Bexley"
    assert council.contest_type == "candidate" and council.party is None
    assert [(c.name_display, c.party, c.kind) for c in council.choices] == [
        ("Ann Lee", "Rep", "candidate"),
        ("Gerald Dixon", "Dem", "candidate"),  # mojibake + NBSP repaired
        ("OVER VOTES", None, "over"),
        ("UNDER VOTES", None, "under"),
    ]
    assert zoo.contest_type == "issue"
    assert [c.kind for c in zoo.choices] == ["yes", "no", "over", "under"]


def test_2025_precincts_keyed_by_padded_name_and_pseudo_rows_split_out(tmp_path):
    _, p = _parse(sheet_2025(), tmp_path)
    assert [x.name for x in p.precincts] == ["COLUMBUS 01-A", "BEXLEY 01-A", "BLENDON-A"]
    assert p.precincts[1].code_raw == "0002" and p.precincts[1].name_raw == "BEXLEY 1-A"
    assert p.out_of_county_names == ["Delaware County"]
    assert sorted(o.votes for o in p.out_of_county) == [1, 5, 10]
    kinds = {n.kind for n in p.normalizations.entries}
    assert {"mojibake", "nbsp", "ward_padding"} <= kinds


def test_2025_all_zero_contest_is_absent_not_zero(tmp_path):
    _, p = _parse(sheet_2025(), tmp_path)
    council_rows = {r.precinct_name for r in p.results if r.contest_ordinal == 0}
    assert council_rows == {"BEXLEY 01-A"}
    assert p.absent_cells == 2
    assert len(p.results) == 4 + 3 * 4


def test_2025_reconciles_with_county_total_row(tmp_path):
    _, p = _parse(sheet_2025(), tmp_path)
    assert len(p.column_checks) == 11
    assert all(c.ok for c in p.column_checks)
    levy_for = next(c for c in p.column_checks if c.label.endswith("For the Tax Levy"))
    assert (levy_for.precinct_sum, levy_for.out_of_county_sum, levy_for.county_total) == (
        115,
        10,
        125,
    )


def test_2025_reconciliation_failure_is_reported_not_hidden(tmp_path):
    sheet = sheet_2025()
    sheet.total_overrides[7] = 999  # levy 'For' total
    _, p = _parse(sheet, tmp_path)
    bad = [c for c in p.column_checks if not c.ok]
    assert len(bad) == 1 and bad[0].county_total == 999


def test_2025_primary_turnout_by_party(tmp_path):
    _, p = _parse(sheet_2025_primary(), tmp_path)
    assert p.contests[0].party == "Dem"
    assert p.contests[0].name_display == "For Mayor - City of Bexley"
    dem = [t for t in p.turnout if t.party == "Dem"]
    assert [(t.registered, t.ballots_cast) for t in dem] == [(40, 20), (90, 30)]


def test_2025_malformed_missing_total_row(tmp_path):
    sheet = sheet_2025()
    grid = sheet.grid()[:-1]
    with pytest.raises(LayoutError, match="county-total"):
        detect_adapter(grid, "x").parse(grid)


def test_2025_malformed_fractional_vote(tmp_path):
    sheet = sheet_2025()
    sheet.cols[7].values[0] = 30.5  # type: ignore[call-overload]
    with pytest.raises(LayoutError, match="whole count"):
        _parse(sheet, tmp_path)


def test_2025_malformed_unknown_party_code(tmp_path):
    sheet = sheet_2025()
    sheet.cols[3].h2 = "Xyz"
    with pytest.raises(LayoutError, match="unknown party code"):
        _parse(sheet, tmp_path)


def test_2025_malformed_other_county_number(tmp_path):
    sheet = sheet_2025()
    sheet.county_number = 18
    with pytest.raises(LayoutError, match="only Franklin"):
        _parse(sheet, tmp_path)


# --- fcboe_wide_2024 ------------------------------------------------------------------


def test_2024_blank_means_not_on_ballot(tmp_path):
    adapter, p = _parse(sheet_2024(), tmp_path)
    assert adapter.name == "fcboe_wide_2024"
    rep = next(c for c in p.contests if "State Representative" in c.name_display)
    on_ballot = {r.precinct_name for r in p.results if r.contest_ordinal == rep.ordinal}
    assert on_ballot == {"COLUMBUS 01-A", "BLENDON-A"}  # BLENDON-A has real zeros
    assert p.absent_cells == 1
    assert all(c.ok for c in p.column_checks)


def test_2024_bare_pseudo_row_name_gets_county_suffix(tmp_path):
    _, p = _parse(sheet_2024(), tmp_path)
    assert p.out_of_county_names == ["Clark County"]
    assert sum(o.votes for o in p.out_of_county) == 13
    assert p.has_over_under is False


def test_2024_primary_party_ballot_columns(tmp_path):
    _, p = _parse(sheet_2024(primary=True), tmp_path)
    assert {c.party for c in p.contests} == {"Dem"}
    assert p.contests[0].name_display == "For U.S. Senator"  # trailing ' -' stripped
    assert {t.party for t in p.turnout} == {"ALL", "Dem"}


def test_2024_malformed_partly_blank_contest(tmp_path):
    sheet = sheet_2024()
    sheet.cols[-1].values[0] = ""  # write-in blank but candidate numeric in same precinct
    with pytest.raises(LayoutError, match="partly blank"):
        _parse(sheet, tmp_path)


def test_2024_malformed_unlabeled_column(tmp_path):
    sheet = sheet_2024()
    sheet.cols.insert(2, Col("Mystery", "Dem", "", [1, 1, 1, 0]))
    with pytest.raises(LayoutError, match="not a known party ballot column"):
        _parse(sheet, tmp_path)


# --- detection ------------------------------------------------------------------------


def test_unknown_layout_raises_specific_error(tmp_path):
    grid: list[list[object]] = [["Precinct", "Votes"], ["", ""], ["", ""], ["A", 1]]
    with pytest.raises(UnknownLayoutError, match="no adapter recognizes"):
        detect_adapter(grid, "weird.xlsx")
