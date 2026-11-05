"""FCBOE wide export with group detail rows, 2023 vintage (sample: 2023 general,
`2023-General-Official-Pct-Level-with-Group-Details.xlsx`: 3,576 rows x 697 columns).

Same columns as the 2025 layout (turnout totals only, OVER / UNDER VOTES, an all-zero contest
is off the ballot, `<X> County` pseudo-rows, a `ZZZ` / `COUNTY TOTALS` row), with these
differences:
- Every precinct has four consecutive rows, one per ballot group. The file does not say which
  group is which, so they are summed (registered voters are equal in all four and checked).
  Nothing is lost: the county-total row reconciles with the sums.
- Precinct codes are numbers (1.0, 2.0, ...), formatted to 4 digits. They are row ordinals.
- Many contest names start with a two-letter jurisdiction code ('CO For Mayor City of
  Columbus'). It is dropped from the display name and logged; `name_raw` keeps the source.
  Ballot issue numbers ('#6 ...') stay: '#6' and '#7' are different Perry Township levies whose
  names are otherwise the same.
"""

import re

from precinctmap.ingest.adapters import fcboe_wide_2025 as wide
from precinctmap.ingest.adapters._fcboe import ID_COLUMNS, LayoutRules, first_row, parse_with
from precinctmap.ingest.adapters._group_rows import collapse_groups, has_group_rows
from precinctmap.ingest.fcboe_common import Grid, cell_str, zero_means_absent
from precinctmap.ingest.model import NormalizationLog, ParsedFile

NAME = "fcboe_wide_2023"
VERSION = "1"
_JURISDICTION_CODE = re.compile(r"^[A-Z]{2}\s+(?=For )")


def detect(grid: Grid) -> bool:
    row1 = first_row(grid)
    return (
        tuple(row1[:3]) == ID_COLUMNS
        and row1[3:4] == ["REGISTERED VOTERS TOTAL"]
        and "BALLOTS CAST TOTAL" in row1
        and len(grid) > 4
        and cell_str(grid[2][3]).strip() == "VOTERS"
        and has_group_rows(grid)
    )


def contest_name(name: str, location: str, log: NormalizationLog) -> str:
    """Drop a leading two-letter jurisdiction code, logging it."""
    stripped = _JURISDICTION_CODE.sub("", name)
    if stripped != name:
        log.add("jurisdiction_code", location, name, stripped)
    return stripped


RULES = LayoutRules(
    NAME,
    VERSION,
    wide.meta_columns,
    wide.classify_row,
    zero_means_absent,
    True,
    contest_name,
)


def parse(grid: Grid) -> ParsedFile:
    group_log = NormalizationLog()
    collapsed = collapse_groups(grid, group_log)
    parsed = parse_with(RULES, collapsed.grid)
    # Source rows point at each precinct's first row in the file, not the collapsed grid.
    parsed.precincts = [
        type(p)(collapsed.first_source_row[p.source_row - 1] + 1, p.code_raw, p.name_raw, p.name)
        for p in parsed.precincts
    ]
    parsed.normalizations.entries[:0] = group_log.entries
    return parsed
