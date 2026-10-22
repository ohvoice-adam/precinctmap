"""FCBOE "classic" wide export, 2020 general (sample: `2020-General-Election.xlsx`, one sheet
'Election Result 2020 With Dist', 894 rows x 1,298 columns).

- Five header rows. Row 5 starts DISTRICT NO, WARD NO, PRECINCT NUMBER, PRECINCT CODE (the BOE
  code, '01001A'), then poll and district attributes, with PRECINCT NAME in column 26.
- Turnout: REGISTERED VOTERS (column 28), then BALLOTS CAST and BALLOTS CAST BLANK, each as
  Absentee, Early Vote, Election Day, Provisoinal [sic], TOTAL.
- Choices from column 39 in blocks of five (layout GENERAL_2020 in `_classic_contests`): row 1
  the contest name (merged blocks), row 2 the choice with its party as a prefix ('Dem Joseph R.
  Biden'), row 3 'Non' (general ballot). Contests end with OVER VOTES, UNDER VOTES; the four
  parts must add up to TOTAL.
- One row per precinct (no splits, no other counties' rows). After blank rows come TOTALS and
  FILTERED TOTALS (label in column 26), which must agree.
- No blank cells: a contest is absent from a precinct's ballot when all its columns are 0.
"""

import re

from precinctmap.ingest.adapters._classic_contests import GENERAL_2020, check_parts, segment
from precinctmap.ingest.errors import LayoutError
from precinctmap.ingest.fcboe_common import (
    Grid,
    as_int,
    build_contest,
    cell_str,
    emit_results,
    loc,
    zero_means_absent,
)
from precinctmap.ingest.fcboe_tally import MetaColumn, emit_turnout, reconcile
from precinctmap.ingest.model import ContestSpec, NormalizationLog, ParsedFile, PrecinctRow
from precinctmap.ingest.normalize import precinct_name

NAME = "fcboe_general_2020"
VERSION = "1"
COUNTY = "Franklin"
ID_COLUMNS = ("DISTRICT NO", "WARD NO", "PRECINCT NUMBER", "PRECINCT CODE")
NAME_COL, REGISTERED_COL = 25, 27
_BALLOTS = (("BALLOTS CAST", 28, "ballots_cast"), ("BALLOTS CAST BLANK", 33, "ballots_blank"))
_TOTALS, _FILTERED = "TOTALS", "FILTERED TOTALS"
_CODE = re.compile(r"\d{5}[A-Z]{1,2}")


def _cell(grid: Grid, r: int, c: int) -> str:
    return cell_str(grid[r][c]).strip() if r < len(grid) and c < len(grid[r]) else ""


def detect(grid: Grid) -> bool:
    return (
        len(grid) > 5
        and tuple(_cell(grid, 4, c) for c in range(4)) == ID_COLUMNS
        and _cell(grid, 4, NAME_COL) == "PRECINCT NAME"
        and _cell(grid, 2, REGISTERED_COL) == "REGISTERED VOTERS"
        and _cell(grid, 4, GENERAL_2020.first_column) == GENERAL_2020.cycle[0]
    )


def meta_columns(grid: Grid) -> list[MetaColumn]:
    meta = [MetaColumn(REGISTERED_COL, "REGISTERED VOTERS", "ALL", "registered")]
    total = len(GENERAL_2020.cycle) - 1
    for label, first, field in _BALLOTS:
        if _cell(grid, 1, first) != label or _cell(grid, 4, first + total) != "TOTAL":
            raise LayoutError(f"column {first + 1}: expected {label!r} ending in a TOTAL column")
        meta.append(MetaColumn(first + total, label, "ALL", field))  # type: ignore[arg-type]
    return meta


def _check_meta_parts(grid: Grid, rows: list[int]) -> None:
    n = len(GENERAL_2020.cycle)
    for r in rows:
        for _, first, _ in _BALLOTS:
            parts = sum(as_int(grid[r][first + i], loc(r, first + i)) or 0 for i in range(n - 1))
            if parts != (as_int(grid[r][first + n - 1], loc(r, first + n - 1)) or 0):
                raise LayoutError(
                    f"{loc(r, first + n - 1)}: ballots TOTAL is not the sum of its parts"
                )


def split_rows(grid: Grid) -> tuple[list[int], int]:
    """Precinct rows (a BOE code in column 4) and the TOTALS row; FILTERED TOTALS must match."""
    r, data = 5, []
    while r < len(grid) and _cell(grid, r, 3):
        data.append(r)
        r += 1
    labeled: dict[str, int] = {}
    for t in range(r, len(grid)):
        if not any(cell_str(v).strip() for v in grid[t]):
            continue
        label = _cell(grid, t, NAME_COL)
        if label not in (_TOTALS, _FILTERED) or label in labeled:
            raise LayoutError(f"row {t + 1}: unexpected row after the precincts ({label!r})")
        labeled[label] = t
    if not data or _TOTALS not in labeled:
        raise LayoutError(f"expected precinct rows and a {_TOTALS!r} row")
    total = labeled[_TOTALS]
    filtered = labeled.get(_FILTERED)
    if filtered is not None and [cell_str(v) for v in grid[filtered][REGISTERED_COL:]] != [
        cell_str(v) for v in grid[total][REGISTERED_COL:]
    ]:
        raise LayoutError(f"rows {total + 1} and {filtered + 1}: {_TOTALS} and {_FILTERED} differ")
    return data, total


def classify_row(grid: Grid, r: int, log: NormalizationLog) -> PrecinctRow:
    code, name = _cell(grid, r, 3), _cell(grid, r, NAME_COL)
    if not _CODE.fullmatch(code):
        raise LayoutError(f"row {r + 1}: precinct code {code!r} is not like '01001A'")
    if not name:
        raise LayoutError(f"row {r + 1}: blank precinct name")
    return PrecinctRow(r + 1, code, name, precinct_name(name, f"precinct {loc(r, NAME_COL)}", log))


def parse(grid: Grid) -> ParsedFile:
    log = NormalizationLog()
    meta = meta_columns(grid)
    data, total_idx = split_rows(grid)
    precincts = [classify_row(grid, r, log) for r in data]
    names = [p.name for p in precincts]
    if len(set(names)) != len(names):
        raise LayoutError(
            f"duplicate precinct names: {sorted({n for n in names if names.count(n) > 1})}"
        )
    keyed = [(r, p.name) for r, p in zip(data, precincts, strict=True)]
    _check_meta_parts(grid, [*data, total_idx])
    cols = segment(grid, log, GENERAL_2020)
    check_parts(grid, [*data, total_idx], cols, GENERAL_2020)
    contests: list[ContestSpec] = [build_contest(i, k.choices, log) for i, k in enumerate(cols)]
    results, absent = emit_results(grid, keyed, contests, zero_means_absent)
    columns = [(m.column, m.label) for m in meta] + [
        (ch.column, f"{c.name_display} | {ch.name_display}") for c in contests for ch in c.choices
    ]
    return ParsedFile(
        adapter=NAME,
        adapter_version=VERSION,
        county=COUNTY,
        contests=contests,
        precincts=precincts,
        results=results,
        turnout=emit_turnout(grid, keyed, meta),
        out_of_county=[],
        out_of_county_names=[],
        column_checks=reconcile(grid, data, [], total_idx, columns),
        absent_cells=absent,
        has_over_under=True,
        normalizations=log,
    )
