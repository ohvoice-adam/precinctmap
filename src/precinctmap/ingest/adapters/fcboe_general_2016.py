"""FCBOE general export, 2016 vintage (sample: `2016-General-Official-Results-with-Overlaps-
and-Precinct-Detail.xlsx`, one sheet 'General 2016', 1,229 rows x 256 columns).

A workbook adapter, because contest spans come from merged cells:
- Row 1 numbers the columns ('001', '002', ...). Row 2 holds each contest's name, merged across
  its choices; row 3 the candidate's party (DEM, REP, GRE or blank); row 4 the choice label, or
  for columns 1-30 the field name (PRECINCT NAME, PRECINCT NAME WITH SPLIT, PRECINCT CODE, poll
  and district attributes, ..., PRECINCT NAME with split number in column 28, REGISTERED VOTERS,
  TOTAL VOTERS).
- Rows are precinct splits ('COLUMBUS 01-B 1', '... 2'); they are summed into their precinct by
  BOE code ('01001B'), and column 1 gives the precinct's name.
- After the splits: 'FRANKLIN COUNTY' (subtotal of the splits), one row per other county for
  joint contests ('Delaware County'), 'OVERLAP COUNTIES ONLY' (their subtotal) and 'COUNTY
  TOTALS'. Each subtotal must match the rows it covers; COUNTY TOTALS is the reconciliation
  total.
- No over/under-vote columns, no blank cells: a contest is off a precinct's ballot when all its
  columns are 0 in every split.
"""

import re

from precinctmap.ingest.adapters._fcboe import pseudo_county
from precinctmap.ingest.errors import LayoutError
from precinctmap.ingest.fcboe_common import Header, as_int, build_contest, cell_str, loc
from precinctmap.ingest.model import (
    ColumnCheck,
    ContestSpec,
    NormalizationLog,
    OutOfCountyRow,
    ParsedFile,
    PrecinctRow,
    ResultRow,
    TurnoutRow,
)
from precinctmap.ingest.normalize import clean_text, precinct_name
from precinctmap.io.xlsx import Sheet

NAME = "fcboe_general_2016"
VERSION = "1"
COUNTY = "Franklin"
ID_COLUMNS = ("PRECINCT NAME", "PRECINCT NAME WITH SPLIT", "PRECINCT CODE")
LABEL_COL, REGISTERED_COL, VOTERS_COL, FIRST_CHOICE = 27, 28, 29, 30
PARTY_CODES = {"DEM": "Dem", "REP": "Rep", "GRE": "Grn", "LIB": "Lib", "": ""}
FRANKLIN, OVERLAP, TOTALS = "FRANKLIN COUNTY", "OVERLAP COUNTIES ONLY", "COUNTY TOTALS"
_CODE = re.compile(r"\d{5}[A-Z]{1,2}")


def _text(sheet: Sheet, r: int, c: int) -> str:
    g = sheet.grid
    return cell_str(g[r][c]).strip() if r < len(g) and c < len(g[r]) else ""


def detect(sheets: list[Sheet]) -> bool:
    if len(sheets) != 1:
        return False
    s = sheets[0]
    return tuple(_text(s, 3, c) for c in range(3)) == ID_COLUMNS and [
        _text(s, 3, c) for c in (LABEL_COL, REGISTERED_COL, VOTERS_COL)
    ] == ["PRECINCT NAME", "REGISTERED VOTERS", "TOTAL VOTERS"]


def _contests(sheet: Sheet, log: NormalizationLog) -> list[list[Header]]:
    """Choice headers per contest; spans from the merged row-2 names."""
    spans = {c1: c2 for (r1, c1), (r2, c2) in sheet.merges if r1 == 1 and r2 == 1}
    width = len(sheet.grid[0])
    last = max((c for c in range(width) if any(_text(sheet, r, c) for r in (1, 2, 3))), default=0)
    out, c = [], FIRST_CHOICE
    while c <= last:
        raw = cell_str(sheet.grid[1][c])
        if not raw.strip():
            raise LayoutError(f"column {c + 1}: column is in no contest (blank row 2)")
        name, run = clean_text(raw, f"header {loc(1, c)}", log), []
        for col in range(c, spans.get(c, c) + 1):
            code = _text(sheet, 2, col)
            if code not in PARTY_CODES:
                raise LayoutError(f"{loc(2, col)}: unknown party code {code!r}")
            label_raw = cell_str(sheet.grid[3][col])
            label = clean_text(label_raw, f"header {loc(3, col)}", log)
            run.append(Header(col, name, PARTY_CODES[code], label, raw, label_raw))
        out.append(run)
        c = spans.get(c, c) + 1
    return out


def _rows(sheet: Sheet) -> tuple[list[int], list[tuple[int, str]], dict[str, int]]:
    """Split rows, other-county rows, and the labeled subtotal/total rows."""
    r, data = 4, []
    while r < len(sheet.grid) and _text(sheet, r, 2):
        if not _CODE.fullmatch(_text(sheet, r, 2)) or not _text(sheet, r, 0):
            raise LayoutError(f"row {r + 1}: precinct code {_text(sheet, r, 2)!r} or name missing")
        data.append(r)
        r += 1
    counties: list[tuple[int, str]] = []
    labeled: dict[str, int] = {}
    for t in range(r, len(sheet.grid)):
        if not any(cell_str(v).strip() for v in sheet.grid[t]):
            continue
        label = _text(sheet, t, LABEL_COL)
        if label in (FRANKLIN, OVERLAP, TOTALS) and label not in labeled:
            labeled[label] = t
        else:
            counties.append((t, pseudo_county(label, f"row {t + 1}")))
    if not data or set(labeled) != {FRANKLIN, OVERLAP, TOTALS}:
        raise LayoutError(f"expected split rows and the rows {FRANKLIN}, {OVERLAP}, {TOTALS}")
    return data, counties, labeled


def _sum(sheet: Sheet, rows: list[int], col: int) -> int:
    return sum(as_int(sheet.grid[r][col], loc(r, col)) or 0 for r in rows)


def _precincts(
    sheet: Sheet, data: list[int], log: NormalizationLog
) -> tuple[list[PrecinctRow], dict[str, list[int]]]:
    splits: dict[str, list[int]] = {}
    for r in data:
        splits.setdefault(_text(sheet, r, 2), []).append(r)
    out = []
    for code, rows in splits.items():
        names = {_text(sheet, r, 0) for r in rows}
        if len(names) != 1:
            raise LayoutError(f"precinct {code}: splits named {sorted(names)}")
        base = names.pop()
        log.add(
            "precinct_splits",
            f"precinct {code}",
            " + ".join(_text(sheet, r, 1) for r in rows),
            base,
        )
        out.append(
            PrecinctRow(rows[0] + 1, code, base, precinct_name(base, f"precinct {code}", log))
        )
    return out, splits


def _checks(
    sheet: Sheet,
    cols: list[tuple[int, str]],
    data: list[int],
    counties: list[tuple[int, str]],
    labeled: dict[str, int],
) -> list[ColumnCheck]:
    county_rows = [r for r, _ in counties]
    out = []
    for col, label in cols:
        mine, theirs = _sum(sheet, data, col), _sum(sheet, county_rows, col)
        if mine != _sum(sheet, [labeled[FRANKLIN]], col) or theirs != _sum(
            sheet, [labeled[OVERLAP]], col
        ):
            raise LayoutError(f"column {col + 1}: {FRANKLIN} or {OVERLAP} doesn't match its rows")
        out.append(ColumnCheck(col, label, mine, theirs, _sum(sheet, [labeled[TOTALS]], col)))
    return out


def _results(
    sheet: Sheet,
    contests: list[ContestSpec],
    precincts: list[PrecinctRow],
    splits: dict[str, list[int]],
) -> tuple[list[ResultRow], int]:
    rows: list[ResultRow] = []
    absent = 0
    for p in precincts:
        for c in contests:
            values = [_sum(sheet, splits[p.code_raw], ch.column) for ch in c.choices]
            if not any(values):
                absent += 1
                continue
            rows += [
                ResultRow(p.name, c.ordinal, ch.ordinal, v)
                for ch, v in zip(c.choices, values, strict=True)
            ]
    return rows, absent


def parse(sheets: list[Sheet]) -> ParsedFile:
    sheet, log = sheets[0], NormalizationLog()
    data, counties, labeled = _rows(sheet)
    precincts, splits = _precincts(sheet, data, log)
    names = [p.name for p in precincts]
    if len(set(names)) != len(names):
        raise LayoutError(
            f"duplicate precinct names: {sorted({n for n in names if names.count(n) > 1})}"
        )
    contests = [build_contest(i, run, log) for i, run in enumerate(_contests(sheet, log))]
    results, absent = _results(sheet, contests, precincts, splits)
    outside = [
        OutOfCountyRow(county, c.ordinal, ch.ordinal, v)
        for r, county in counties
        for c in contests
        for ch in c.choices
        if (v := _sum(sheet, [r], ch.column))
    ]
    turnout = [
        TurnoutRow(
            p.name,
            "ALL",
            _sum(sheet, splits[p.code_raw], REGISTERED_COL),
            _sum(sheet, splits[p.code_raw], VOTERS_COL),
            None,
        )
        for p in precincts
    ]
    cols = [(REGISTERED_COL, "REGISTERED VOTERS"), (VOTERS_COL, "TOTAL VOTERS")] + [
        (ch.column, f"{c.name_display} | {ch.name_display}") for c in contests for ch in c.choices
    ]
    return ParsedFile(
        adapter=NAME,
        adapter_version=VERSION,
        county=COUNTY,
        contests=contests,
        precincts=precincts,
        results=results,
        turnout=turnout,
        out_of_county=outside,
        out_of_county_names=[name for _, name in counties],
        column_checks=_checks(sheet, cols, data, counties, labeled),
        absent_cells=absent,
        has_over_under=False,
        normalizations=log,
    )
