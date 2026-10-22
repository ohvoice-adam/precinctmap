"""One sheet of the FCBOE 2016 multi-sheet export (see fcboe_sheets_2016).

Rows 1-3 are headers: row 1 the contest name (merged across its choices), row 2 the choice
label (or a turnout label), row 3 the party code (DEM, REP, GRE; blank on the issues sheet) or
'PRECINCT NAME'. Data rows follow, one per precinct *split*; after a blank row come the
'FRANKLIN COUNTY ONLY' (turnout only) and 'FRANKLIN COUNTY FILTERED TOTALS' (every column).
"""

import re
from dataclasses import dataclass, field

from precinctmap.ingest.errors import LayoutError
from precinctmap.ingest.fcboe_common import Header, cell_str, loc
from precinctmap.ingest.model import NormalizationLog
from precinctmap.ingest.normalize import clean_text
from precinctmap.io.xlsx import Sheet

ID_COLUMNS = ("DISTRICT NUMBER", "WARD NUMBER", "PRECINCT CODE", "PRECINCT CODE WITH SPLIT")
TURNOUT = ("REGISTERED VOTERS", "TOTAL VOTERS", "DEMOCRATIC", "REPUBLICAN", "GREEN")
PARTY_CODES = {"DEM": "Dem", "REP": "Rep", "GRE": "Grn", "": None}
TOTAL_ONLY, TOTAL_FILTER = "FRANKLIN COUNTY ONLY", "FRANKLIN COUNTY FILTERED TOTALS"
_CODE = re.compile(r"\d{5}[A-Z]{1,2}")


@dataclass
class SheetLayout:
    sheet: Sheet
    party: str | None
    name_col: int  # PRECINCT NAME
    turnout_cols: list[int]  # REGISTERED VOTERS, TOTAL VOTERS, DEMOCRATIC, REPUBLICAN, GREEN
    contests: list[list[Header]] = field(default_factory=list)  # choice headers per contest
    data_rows: list[int] = field(default_factory=list)
    filter_row: int = -1
    only_row: int | None = None


def _text(sheet: Sheet, r: int, c: int) -> str:
    g = sheet.grid
    return cell_str(g[r][c]).strip() if r < len(g) and c < len(g[r]) else ""


def detect_sheet(sheet: Sheet) -> bool:
    return tuple(_text(sheet, 1, c) for c in range(4)) == ID_COLUMNS


def read_layout(sheet: Sheet, party: str | None, log: NormalizationLog) -> SheetLayout:
    width = len(sheet.grid[0]) if sheet.grid else 0
    name_col = next((c for c in range(width) if _text(sheet, 2, c) == "PRECINCT NAME"), None)
    if name_col is None:
        raise LayoutError(f"sheet {sheet.name!r}: no PRECINCT NAME header in row 3")
    turnout = list(range(name_col + 1, name_col + 1 + len(TURNOUT)))
    got = tuple(_text(sheet, 1, c) for c in turnout)
    if got != TURNOUT:
        raise LayoutError(
            f"sheet {sheet.name!r}: turnout headers {list(got)}, expected {list(TURNOUT)}"
        )
    layout = SheetLayout(sheet, party, name_col, turnout)
    layout.contests = _contests(sheet, party, turnout[-1] + 1, log)
    _rows(layout)
    return layout


def _contests(
    sheet: Sheet, party: str | None, first: int, log: NormalizationLog
) -> list[list[Header]]:
    """Contest spans from the merged row-1 names; a single-choice contest is one unmerged cell."""
    spans = {c1: c2 for (r1, c1), (r2, c2) in sheet.merges if r1 == 0 and r2 == 0}
    last = max(
        (c for c in range(len(sheet.grid[0])) if any(_text(sheet, r, c) for r in range(3))),
        default=first - 1,
    )
    out, c = [], first
    while c <= last:
        raw = cell_str(sheet.grid[0][c])
        if not raw.strip():
            raise LayoutError(
                f"sheet {sheet.name!r} column {c + 1}: column is in no contest (blank row 1)"
            )
        end = spans.get(c, c)
        name = clean_text(raw, f"{sheet.name} header {loc(0, c)}", log)
        run = []
        for col in range(c, end + 1):
            code = _text(sheet, 2, col)
            if code not in PARTY_CODES or PARTY_CODES[code] != party:
                raise LayoutError(
                    f"sheet {sheet.name!r} {loc(2, col)}: party code {code!r} on the {party} sheet"
                )
            label_raw = cell_str(sheet.grid[1][col])
            label = clean_text(label_raw, f"{sheet.name} header {loc(1, col)}", log)
            run.append(Header(col, name, party or "", label, raw, label_raw))
        out.append(run)
        c = end + 1
    return out


def _rows(layout: SheetLayout) -> None:
    """Split rows (a precinct code in column 3), then a blank row, then the labeled totals."""
    sheet, g = layout.sheet, layout.sheet.grid
    r = 3
    while r < len(g) and _text(sheet, r, 2):
        if not _CODE.fullmatch(_text(sheet, r, 2)):
            raise LayoutError(
                f"sheet {sheet.name!r} row {r + 1}: precinct code {_text(sheet, r, 2)!r}"
            )
        layout.data_rows.append(r)
        r += 1
    for t in range(r, len(g)):
        if not any(cell_str(v).strip() for v in g[t]):
            continue
        label = _text(sheet, t, layout.name_col)
        if label == TOTAL_FILTER:
            layout.filter_row = t
        elif label == TOTAL_ONLY:
            layout.only_row = t
        else:
            raise LayoutError(
                f"sheet {sheet.name!r} row {t + 1}: unexpected row after the precincts ({label!r})"
            )
    if not layout.data_rows or layout.filter_row < 0:
        raise LayoutError(f"sheet {sheet.name!r}: expected split rows and a {TOTAL_FILTER!r} row")
