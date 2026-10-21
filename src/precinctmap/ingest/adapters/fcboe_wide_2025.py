"""FCBOE wide export, 2025+ vintage (samples: 2025 primary, 2025 general, 2026 primary).

- Turnout: `REGISTERED VOTERS TOTAL`, `REGISTERED VOTERS - <Party>`, `BALLOTS CAST TOTAL`,
  `BALLOTS CAST - <Party>`, `BALLOTS CAST BLANK`; party code in row 2.
- Precinct codes are 4-digit row ordinals; they shift between elections. Never a key.
- Out-of-county pseudo-rows are named `<X> County` with registered = 0.
- No blank cells. Every contest ends with OVER VOTES / UNDER VOTES. A contest absent from a
  precinct's ballot is all zeros.
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
    KNOWN_PARTIES,
    NONPARTISAN,
    Grid,
    Header,
    as_int,
    cell_str,
    loc,
    zero_means_absent,
)
from precinctmap.ingest.fcboe_tally import MetaColumn
from precinctmap.ingest.model import NormalizationLog, ParsedFile, PrecinctRow, TurnoutField
from precinctmap.ingest.normalize import precinct_name

NAME = "fcboe_wide_2025"
VERSION = "1"
_CODE = re.compile(r"\d{4}")
_COUNTY_ROW = re.compile(r"[A-Z][a-z]+(?: [A-Z][a-z]+)* County")


def detect(grid: Grid) -> bool:
    row1 = first_row(grid)
    return (
        tuple(row1[:3]) == ID_COLUMNS
        and row1[3:4] == ["REGISTERED VOTERS TOTAL"]
        and "BALLOTS CAST TOTAL" in row1
        and len(grid) > 2
        and cell_str(grid[2][3]).strip() == "VOTERS"
    )


def _meta_column(h: Header) -> MetaColumn | None:
    fixed: dict[str, tuple[str, TurnoutField]] = {
        "REGISTERED VOTERS TOTAL": ("ALL", "registered"),
        "BALLOTS CAST TOTAL": ("ALL", "ballots_cast"),
        "BALLOTS CAST BLANK": ("ALL", "ballots_blank"),
    }
    if h.h1 in fixed:
        party, field = fixed[h.h1]
        return MetaColumn(h.column, h.h1, party, field)
    prefixed: tuple[tuple[str, TurnoutField], ...] = (
        ("REGISTERED VOTERS - ", "registered"),
        ("BALLOTS CAST - ", "ballots_cast"),
    )
    for prefix, pfield in prefixed:
        if h.h1.startswith(prefix):
            if h.h2 not in KNOWN_PARTIES | {NONPARTISAN}:
                raise LayoutError(f"column {h.column + 1}: unknown party code {h.h2!r}")
            return MetaColumn(h.column, h.h1, h.h2, pfield)
    if h.h1.startswith(("REGISTERED VOTERS", "BALLOTS CAST")):
        raise LayoutError(f"column {h.column + 1}: unrecognized turnout column {h.h1!r}")
    return None


def meta_columns(headers: list[Header]) -> list[MetaColumn]:
    meta = []
    for h in headers[3:]:
        m = _meta_column(h)
        if m is None:
            break
        meta.append(m)
    have = {(m.party, m.field) for m in meta}
    if not {("ALL", "registered"), ("ALL", "ballots_cast")} <= have:
        raise LayoutError("missing REGISTERED VOTERS TOTAL or BALLOTS CAST TOTAL")
    return meta


def classify_row(grid: Grid, r: int, log: NormalizationLog) -> PrecinctRow | str:
    code, name = cell_str(grid[r][1]).strip(), cell_str(grid[r][2])
    if _COUNTY_ROW.fullmatch(name.strip()):
        if as_int(grid[r][3], loc(r, 3)):
            raise LayoutError(f"row {r + 1}: out-of-county row {name!r} has registered voters")
        return pseudo_county(name, f"row {r + 1}")
    if not _CODE.fullmatch(code):
        raise LayoutError(f"row {r + 1}: precinct code {code!r} is not 4 digits")
    if not name.strip():
        raise LayoutError(f"row {r + 1}: blank precinct name")
    return PrecinctRow(r + 1, code, name, precinct_name(name, f"precinct {loc(r, 2)}", log))


RULES = LayoutRules(NAME, VERSION, meta_columns, classify_row, zero_means_absent, True)


def parse(grid: Grid) -> ParsedFile:
    return parse_with(RULES, grid)
