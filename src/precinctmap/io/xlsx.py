"""Spreadsheet reading. Most results files are single-sheet workbooks; multi-sheet layouts
(2016: one sheet per party ballot) are read whole, with their merged-cell ranges, and only a
workbook adapter may accept them."""

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from python_calamine import CalamineWorkbook

from precinctmap.ingest.errors import LayoutError

Grid = list[list[object]]
#: ((first_row, first_col), (last_row, last_col)), 0-based and inclusive.
Merge = tuple[tuple[int, int], tuple[int, int]]


@dataclass(frozen=True)
class Sheet:
    name: str
    grid: Grid  # rectangular; '' for empty cells
    merges: list[Merge]


def _rectangular(rows: Sequence[Sequence[object]]) -> Grid:
    width = max((len(r) for r in rows), default=0)
    return [list(r) + [""] * (width - len(r)) for r in rows]


def read_workbook(path: Path) -> list[Sheet]:
    """Every sheet of `path`, in workbook order."""
    wb = CalamineWorkbook.from_path(str(path))
    sheets = []
    for name in wb.sheet_names:
        sh = wb.get_sheet_by_name(name)
        merges = [((a[0], a[1]), (b[0], b[1])) for a, b in (sh.merged_cell_ranges or [])]
        sheets.append(Sheet(name, _rectangular(sh.to_python(skip_empty_area=False)), merges))
    if not sheets:
        raise LayoutError(f"{path.name}: workbook has no sheets")
    return sheets


def read_single_sheet(path: Path) -> Grid:
    """Return the only sheet of `path` as a rectangular grid ('' for empty cells).

    Raises LayoutError when the workbook has zero or several sheets, so a multi-sheet
    layout is never silently half-read.
    """
    wb = CalamineWorkbook.from_path(str(path))
    names = list(wb.sheet_names)
    if len(names) != 1:
        raise LayoutError(f"{path.name}: expected exactly one sheet, found {names}")
    return _rectangular(wb.get_sheet_by_name(names[0]).to_python(skip_empty_area=False))
