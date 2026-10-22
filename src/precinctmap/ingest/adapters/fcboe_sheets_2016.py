"""FCBOE multi-sheet export, 2016 vintage (sample: 2016 primary, `2016-Official-Primary-
Results-Precinct-Level.xlsx`: sheets Democratic, Republican, Green, Questions & Issues).

- Each sheet repeats the precinct and turnout columns (registered, total voters, ballots by
  party) and must agree on them; contests follow (layout in `_sheets_2016`).
- Rows are precinct *splits* ('01001B-1', 'COLUMBUS 01-B 01'), parts of a precinct with
  different districts. Splits are summed into their precinct by BOE code ('01001B'); the
  name drops the split number ('COLUMBUS 01-B'), which is logged.
- No over/under-vote columns and no blank cells: a contest is off a precinct's ballot when all
  its columns are 0 in every split.
- Totals: the 'FRANKLIN COUNTY FILTERED TOTALS' row (all columns); 'FRANKLIN COUNTY ONLY'
  repeats the turnout and must agree. No other counties' rows.
"""

import dataclasses
import re

from precinctmap.ingest.adapters._sheets_2016 import SheetLayout, detect_sheet, read_layout
from precinctmap.ingest.errors import LayoutError
from precinctmap.ingest.fcboe_common import as_int, build_contest, cell_str, loc
from precinctmap.ingest.model import (
    ColumnCheck,
    ContestSpec,
    NormalizationLog,
    ParsedFile,
    PrecinctRow,
    ResultRow,
    TurnoutRow,
)
from precinctmap.ingest.normalize import precinct_name
from precinctmap.io.xlsx import Sheet

NAME = "fcboe_sheets_2016"
VERSION = "1"
COUNTY = "Franklin"
SHEET_PARTIES = {
    "Democratic": "Dem",
    "Republican": "Rep",
    "Green": "Grn",
    "Questions & Issues": None,
}
_SPLIT_NAME = re.compile(r"^(.*\S) (\d{2})$")  # 'COLUMBUS 01-B 02' -> 'COLUMBUS 01-B'


def detect(sheets: list[Sheet]) -> bool:
    return all(s.name in SHEET_PARTIES for s in sheets) and all(detect_sheet(s) for s in sheets)


def _cells(layout: SheetLayout, r: int, cols: list[int]) -> list[int]:
    g = layout.sheet.grid
    return [as_int(g[r][c], f"{layout.sheet.name} {loc(r, c)}") or 0 for c in cols]


def _rows_key(lay: SheetLayout) -> list[tuple[object, ...]]:
    """Per split row: code, split, and the five turnout counts. Every sheet must match."""
    return [
        (_cell(lay, r, 2), _cell(lay, r, 3), *_cells(lay, r, lay.turnout_cols))
        for r in lay.data_rows
    ]


def _check_sheets_agree(layouts: list[SheetLayout]) -> None:
    """Same split rows and the same turnout on every sheet (the turnout is read once)."""
    ref = layouts[0]
    want = _rows_key(ref)
    for lay in layouts[1:]:
        if _rows_key(lay) != want:
            raise LayoutError(
                f"sheets {ref.sheet.name!r} and {lay.sheet.name!r} disagree on precincts or turnout"
            )
    for lay in layouts:
        if lay.only_row is not None and _cells(lay, lay.only_row, lay.turnout_cols) != _cells(
            lay, lay.filter_row, lay.turnout_cols
        ):
            raise LayoutError(
                f"sheet {lay.sheet.name!r}: county-only and filter turnout totals differ"
            )


def _cell(layout: SheetLayout, r: int, c: int) -> str:
    return cell_str(layout.sheet.grid[r][c]).strip()


def _precincts(
    ref: SheetLayout, log: NormalizationLog
) -> tuple[list[PrecinctRow], dict[str, list[int]]]:
    """Precincts in sheet order, and each one's split rows (keyed by BOE code)."""
    splits: dict[str, list[int]] = {}
    bases: dict[str, str] = {}
    for r in ref.data_rows:
        code, raw = _cell(ref, r, 2), _cell(ref, r, ref.name_col)
        m = _SPLIT_NAME.match(raw)
        if not m:
            raise LayoutError(
                f"{ref.sheet.name} {loc(r, ref.name_col)}: {raw!r} has no split number"
            )
        if bases.setdefault(code, m.group(1)) != m.group(1):
            raise LayoutError(f"precinct {code}: splits named {bases[code]!r} and {m.group(1)!r}")
        splits.setdefault(code, []).append(r)
    rows = []
    for code, rs in splits.items():
        parts = [_cell(ref, r, ref.name_col) for r in rs]
        log.add("precinct_splits", f"precinct {code}", " + ".join(parts), bases[code])
        name = precinct_name(bases[code], f"precinct {code}", log)
        rows.append(PrecinctRow(rs[0] + 1, code, bases[code], name))
    return rows, splits


def _sum(layout: SheetLayout, rows: list[int], cols: list[int]) -> list[int]:
    totals = [0] * len(cols)
    for r in rows:
        for i, v in enumerate(_cells(layout, r, cols)):
            totals[i] += v
    return totals


def _contest_specs(
    layouts: list[SheetLayout], log: NormalizationLog
) -> list[tuple[SheetLayout, ContestSpec]]:
    out: list[tuple[SheetLayout, ContestSpec]] = []
    for lay in layouts:
        for run in lay.contests:
            spec = build_contest(len(out), run, log)
            choices = tuple(dataclasses.replace(ch, sheet=lay.sheet.name) for ch in spec.choices)
            out.append((lay, dataclasses.replace(spec, party=lay.party, choices=choices)))
    return out


def _results(
    specs: list[tuple[SheetLayout, ContestSpec]],
    precincts: list[PrecinctRow],
    splits: dict[str, list[int]],
) -> tuple[list[ResultRow], int]:
    rows: list[ResultRow] = []
    absent = 0
    for p in precincts:
        for lay, c in specs:
            values = _sum(lay, splits[p.code_raw], [ch.column for ch in c.choices])
            if not any(values):
                absent += 1
                continue
            rows.extend(
                ResultRow(p.name, c.ordinal, ch.ordinal, v)
                for ch, v in zip(c.choices, values, strict=True)
            )
    return rows, absent


def _turnout(
    ref: SheetLayout, precincts: list[PrecinctRow], splits: dict[str, list[int]]
) -> list[TurnoutRow]:
    out = []
    for p in precincts:
        reg, total, dem, rep, grn = _sum(ref, splits[p.code_raw], ref.turnout_cols)
        out.append(TurnoutRow(p.name, "ALL", reg, total, None))
        out += [
            TurnoutRow(p.name, party, None, n, None)
            for party, n in (("Dem", dem), ("Rep", rep), ("Grn", grn))
        ]
    return out


def _checks(ref: SheetLayout, specs: list[tuple[SheetLayout, ContestSpec]]) -> list[ColumnCheck]:
    def check(lay: SheetLayout, col: int, label: str) -> ColumnCheck:
        got = _sum(lay, lay.data_rows, [col])[0]
        total = _cells(lay, lay.filter_row, [col])[0]
        return ColumnCheck(col, f"{lay.sheet.name}: {label}", got, 0, total, lay.sheet.name)

    out = [check(ref, c, _cell(ref, 1, c)) for c in ref.turnout_cols]
    for lay, c in specs:
        out += [check(lay, ch.column, f"{c.name_display} | {ch.name_display}") for ch in c.choices]
    return out


def parse(sheets: list[Sheet]) -> ParsedFile:
    log = NormalizationLog()
    layouts = [read_layout(s, SHEET_PARTIES[s.name], log) for s in sheets]
    _check_sheets_agree(layouts)
    ref = layouts[0]
    precincts, splits = _precincts(ref, log)
    names = [p.name for p in precincts]
    if len(set(names)) != len(names):
        raise LayoutError(
            f"duplicate precinct names: {sorted({n for n in names if names.count(n) > 1})}"
        )
    specs = _contest_specs(layouts, log)
    results, absent = _results(specs, precincts, splits)
    return ParsedFile(
        adapter=NAME,
        adapter_version=VERSION,
        county=COUNTY,
        contests=[c for _, c in specs],
        precincts=precincts,
        results=results,
        turnout=_turnout(ref, precincts, splits),
        out_of_county=[],
        out_of_county_names=[],
        column_checks=_checks(ref, specs),
        absent_cells=absent,
        has_over_under=False,
        normalizations=log,
    )
