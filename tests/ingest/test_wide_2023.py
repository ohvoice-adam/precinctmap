"""fcboe_wide_2023: group detail rows summed per precinct, numeric codes, prefixed contest names."""

from pathlib import Path

import pytest

from precinctmap.ingest.detect import detect_adapter, parse_file
from precinctmap.ingest.errors import LayoutError
from precinctmap.io.xlsx import read_single_sheet
from tests.fixtures.builders import Sheet, sheet_2025


def _grid_2023(groups: int = 2) -> list[list[object]]:
    """The 2025 fixture reshaped to the 2023 layout: each data row becomes `groups` rows.

    Votes and ballots cast are split into parts (first part takes the remainder); registered
    voters repeat; codes are floats; the contest names get a code and an issue number.
    """
    grid = sheet_2025().grid()
    header, body, total = grid[:3], grid[3:-1], grid[-1]
    header[0] = [
        {
            "For Member of Council City of Bexley": "BE For Member of Council City of Bexley",
            "#1 Proposed Tax Levy - Zoo": "#1  Proposed Tax Levy - Zoo",
        }.get(str(h), h)
        for h in header[0]
    ]
    out: list[list[object]] = list(header)
    for i, row in enumerate(body, start=1):
        for g in range(groups):
            cells = [
                v if c == 3 else (v // groups + (v % groups if g == 0 else 0))
                for c, v in enumerate(row[3:], start=3)
            ]
            out.append([row[0], float(i), row[2], *cells])
    out.append(total)
    return out


def _parse(grid: list[list[object]], name: str = "f.xlsx"):
    adapter = detect_adapter(grid, name)
    return adapter, adapter.parse(grid)


def test_group_rows_are_summed_and_reconcile_with_the_total_row():
    adapter, p = _parse(_grid_2023())
    assert adapter.name == "fcboe_wide_2023"
    assert [x.name for x in p.precincts] == ["COLUMBUS 01-A", "BEXLEY 01-A", "BLENDON-A"]
    assert all(c.ok for c in p.column_checks)
    levy_for = next(c for c in p.column_checks if c.label.endswith("For the Tax Levy"))
    assert (levy_for.precinct_sum, levy_for.out_of_county_sum, levy_for.county_total) == (
        115,
        10,
        125,
    )
    turnout = {t.precinct_name: (t.registered, t.ballots_cast) for t in p.turnout}
    assert turnout["BEXLEY 01-A"] == (200, 80)  # registered not doubled, ballots summed


def test_codes_are_four_digit_and_source_rows_point_at_first_group_row():
    _, p = _parse(_grid_2023(groups=3))
    assert [x.code_raw for x in p.precincts] == ["0001", "0002", "0003"]
    assert [x.source_row for x in p.precincts] == [4, 7, 10]
    kinds = {n.kind for n in p.normalizations.entries}
    assert {"group_rows", "precinct_code", "jurisdiction_code"} <= kinds


def test_contest_prefixes_dropped_from_display_but_kept_in_name_raw():
    _, p = _parse(_grid_2023())
    council, zoo = p.contests
    assert council.name_display == "For Member of Council City of Bexley"
    assert council.name_raw == "BE For Member of Council City of Bexley"
    assert council.jurisdiction == "City of Bexley"
    assert zoo.name_display == zoo.name_raw.replace("  ", " ") == "#1 Proposed Tax Levy - Zoo"


def test_2025_layout_is_not_claimed_by_the_2023_adapter():
    assert detect_adapter(sheet_2025().grid(), "x").name == "fcboe_wide_2025"


def test_parse_file_reads_a_written_workbook(tmp_path: Path):
    path = tmp_path / "2023-General-Official.xlsx"
    sheet = Sheet([("1", "X")], [])  # only to reuse the writer
    sheet.grid = lambda: _grid_2023()  # type: ignore[method-assign]
    sheet.write(path)
    assert read_single_sheet(path)[3][1] == 1  # numeric code survives the round trip
    assert parse_file(path).adapter == "fcboe_wide_2023"


def test_malformed_registered_voters_differ_between_group_rows():
    grid = _grid_2023()
    grid[4][3] = 999
    with pytest.raises(LayoutError, match="registered voters differ"):
        _parse(grid)


def test_malformed_uneven_group_sizes():
    grid = _grid_2023()
    del grid[6]  # the second precinct loses one of its two rows
    with pytest.raises(LayoutError, match="different numbers of group rows"):
        _parse(grid)


def test_malformed_missing_total_row():
    grid = _grid_2023()[:-1]
    with pytest.raises(LayoutError, match="county-total"):
        _parse(grid)


def test_malformed_fractional_vote_in_a_group_row():
    grid = _grid_2023()
    grid[3][8] = 2.5
    with pytest.raises(LayoutError, match="whole count"):
        _parse(grid)


def test_malformed_two_contests_that_differ_only_by_code():
    grid = _grid_2023()
    zoo_cols = [c for c, h in enumerate(grid[0]) if str(h).startswith("#1")]
    for c in zoo_cols[:2]:
        grid[0][c] = "XX For Zoo"
    for c in zoo_cols[2:]:
        grid[0][c] = "For Zoo"
    with pytest.raises(LayoutError, match="both become"):
        _parse(grid)
