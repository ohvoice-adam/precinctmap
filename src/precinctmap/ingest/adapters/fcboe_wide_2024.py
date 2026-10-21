"""FCBOE wide export, 2024 vintage (samples: 2024 primary, 2024 general).

- Turnout: `REGISTERED VOTERS`, `TOTAL VOTERS` (ballots cast); primaries add per-party ballot
  columns named `Democratic`, `Republican`, ... with the code in row 2 and row 3 blank.
- Precinct codes are 3 letters (`AAN`); out-of-county pseudo-rows have a blank code and a
  name like `Clark County` (primary) or bare `Clark` (general).
- No OVER / UNDER VOTES columns. A blank cell means the contest was not on that precinct's
  ballot; it is never a zero.
"""

import re

from precinctmap.ingest.adapters._fcboe import (
    ID_COLUMNS,
    LayoutRules,
    first_row,
    parse_with,
    pseudo_county,
)
from precinctmap.ingest.errors import LayoutError
from precinctmap.ingest.fcboe_common import (
    Grid,
    Header,
    as_int,
    blank_means_absent,
    cell_str,
    loc,
)
from precinctmap.ingest.fcboe_tally import MetaColumn
from precinctmap.ingest.model import NormalizationLog, ParsedFile, PrecinctRow
from precinctmap.ingest.normalize import precinct_name

NAME = "fcboe_wide_2024"
VERSION = "1"
_CODE = re.compile(r"[A-Z]{3}")
_PARTY_BALLOT_COLUMNS = {
    "Democratic": "Dem",
    "Republican": "Rep",
    "Libertarian": "Lib",
    "Green": "Grn",
}


def detect(grid: Grid) -> bool:
    row1 = first_row(grid)
    return tuple(row1[:3]) == ID_COLUMNS and row1[3:5] == ["REGISTERED VOTERS", "TOTAL VOTERS"]


def meta_columns(headers: list[Header]) -> list[MetaColumn]:
    meta = [
        MetaColumn(3, "REGISTERED VOTERS", "ALL", "registered"),
        MetaColumn(4, "TOTAL VOTERS", "ALL", "ballots_cast"),
    ]
    for h in headers[5:]:
        if h.h3:
            break
        code = _PARTY_BALLOT_COLUMNS.get(h.h1)
        if code is None or h.h2 != code:
            raise LayoutError(
                f"column {h.column + 1}: {h.h1!r}/{h.h2!r} has no choice label and is not a "
                "known party ballot column"
            )
        meta.append(MetaColumn(h.column, h.h1, code, "ballots_cast"))
    return meta


def classify_row(grid: Grid, r: int, log: NormalizationLog) -> PrecinctRow | str:
    code, name = cell_str(grid[r][1]).strip(), cell_str(grid[r][2])
    if not code:
        if as_int(grid[r][3], loc(r, 3)):
            raise LayoutError(f"row {r + 1}: out-of-county row {name!r} has registered voters")
        return pseudo_county(name, f"row {r + 1}")
    if not _CODE.fullmatch(code):
        raise LayoutError(f"row {r + 1}: precinct code {code!r} is not 3 letters")
    if not name.strip():
        raise LayoutError(f"row {r + 1}: blank precinct name")
    return PrecinctRow(r + 1, code, name, precinct_name(name, f"precinct {loc(r, 2)}", log))


RULES = LayoutRules(NAME, VERSION, meta_columns, classify_row, blank_means_absent, False)


def parse(grid: Grid) -> ParsedFile:
    return parse_with(RULES, grid)
