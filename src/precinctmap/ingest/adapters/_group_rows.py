"""Collapse a wide export's repeated 'group detail' rows into one row per precinct.

Some exports (2023 general) give every precinct several consecutive rows, one per ballot group
(the file does not label the groups). A precinct's votes and ballots cast are the sum of its
rows; registered voters are the same in every row and are checked, never summed.
"""

from dataclasses import dataclass

from precinctmap.ingest.errors import LayoutError
from precinctmap.ingest.fcboe_common import TOTAL_CODE, Grid, as_int, cell_str, loc
from precinctmap.ingest.model import NormalizationLog

CODE_COL, NAME_COL, REGISTERED_COL, FIRST_SUMMED_COL = 1, 2, 3, 4


@dataclass(frozen=True)
class Collapsed:
    grid: Grid
    #: collapsed data row index -> 0-based index of that precinct's first source row
    first_source_row: dict[int, int]


def has_group_rows(grid: Grid) -> bool:
    """True when the first two data rows are the same precinct (code and name)."""
    if len(grid) < 5:
        return False
    a, b = grid[3], grid[4]
    return bool(cell_str(a[NAME_COL]).strip()) and (a[CODE_COL], a[NAME_COL]) == (
        b[CODE_COL],
        b[NAME_COL],
    )


def _code(value: object, where: str, log: NormalizationLog) -> str:
    """Numeric ordinals (1.0) become the 4-digit text form later layouts use ('0001')."""
    if isinstance(value, str):
        return value
    n = as_int(value, where)
    if n is None:
        raise LayoutError(f"{where}: blank precinct code")
    out = f"{n:04d}"
    log.add("precinct_code", where, cell_str(value), out)
    return out


def _merge(rows: list[int], grid: Grid, code: str) -> list[object]:
    first = grid[rows[0]]
    merged: list[object] = [first[0], code, first[NAME_COL]]
    for c in range(3, len(first)):
        values = [as_int(grid[r][c], loc(r, c)) for r in rows]
        if None in values:
            raise LayoutError(f"{loc(rows[values.index(None)], c)}: unexpected blank cell")
        ints = [v for v in values if v is not None]
        if c == REGISTERED_COL:
            if len(set(ints)) != 1:
                raise LayoutError(
                    f"rows {rows[0] + 1}-{rows[-1] + 1} ({first[NAME_COL]}): registered voters "
                    f"differ between group rows: {ints}"
                )
            merged.append(ints[0])
        else:
            merged.append(sum(ints))
    return merged


def collapse_groups(grid: Grid, log: NormalizationLog) -> Collapsed:
    """Sum each precinct's consecutive rows; the `ZZZ` total row must be a single row."""
    body_end = max(i for i in range(3, len(grid)) if any(cell_str(v).strip() for v in grid[i]))
    groups: list[list[int]] = []
    for r in range(3, body_end + 1):
        if not any(cell_str(v).strip() for v in grid[r]):
            raise LayoutError(f"row {r + 1}: blank row inside the data block")
        key = (grid[r][CODE_COL], grid[r][NAME_COL])
        if groups and (grid[groups[-1][0]][CODE_COL], grid[groups[-1][0]][NAME_COL]) == key:
            groups[-1].append(r)
        else:
            groups.append([r])
    *precincts, total = groups
    if len(total) != 1 or cell_str(grid[total[0]][CODE_COL]) != TOTAL_CODE:
        raise LayoutError(f"last row {body_end + 1} is not a single {TOTAL_CODE} county-total row")
    sizes = {len(g) for g in precincts}
    if len(sizes) != 1:
        raise LayoutError(f"precincts have different numbers of group rows: {sorted(sizes)}")
    out: Grid = [list(grid[0]), list(grid[1]), list(grid[2])]
    first_source: dict[int, int] = {}
    for rows in precincts:
        name = cell_str(grid[rows[0]][NAME_COL])
        where = f"precinct row {rows[0] + 1}"
        code = _code(grid[rows[0]][CODE_COL], where, log)
        first_source[len(out)] = rows[0]
        out.append(_merge(rows, grid, code))
        log.add("group_rows", where, f"{len(rows)} rows (r{rows[0] + 1}-r{rows[-1] + 1})", name)
    out.append(list(grid[total[0]]))
    return Collapsed(out, first_source)
