"""Spreadsheet reading. Results files are single-sheet workbooks; anything else is an error."""

from pathlib import Path

from python_calamine import CalamineWorkbook

from precinctmap.ingest.errors import LayoutError


def read_single_sheet(path: Path) -> list[list[object]]:
    """Return the only sheet of `path` as a rectangular grid ('' for empty cells).

    Raises LayoutError when the workbook has zero or several sheets, so a multi-sheet
    layout is never silently half-read.
    """
    wb = CalamineWorkbook.from_path(str(path))
    names = list(wb.sheet_names)
    if len(names) != 1:
        raise LayoutError(f"{path.name}: expected exactly one sheet, found {names}")
    rows = wb.get_sheet_by_name(names[0]).to_python(skip_empty_area=False)
    width = max((len(r) for r in rows), default=0)
    grid: list[list[object]] = []
    for r in rows:
        line: list[object] = list(r)
        grid.append(line + [""] * (width - len(line)))
    return grid
