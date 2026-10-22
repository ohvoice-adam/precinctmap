"""Format detection: exactly one adapter must claim a file, or ingest stops.

Grid adapters see a single sheet's cells. Workbook adapters see every sheet with its merged
cells (multi-sheet files, and single-sheet layouts whose contest spans are merged cells).
Exactly one adapter of either kind must claim a file.
"""

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from precinctmap.ingest.adapters import (
    fcboe_classic_2020,
    fcboe_general_2016,
    fcboe_general_2020,
    fcboe_sheets_2016,
    fcboe_wide_2024,
    fcboe_wide_2025,
)
from precinctmap.ingest.errors import AmbiguousLayoutError, UnknownLayoutError
from precinctmap.ingest.fcboe_common import Grid
from precinctmap.ingest.model import ParsedFile
from precinctmap.io.xlsx import Sheet, read_workbook


@dataclass(frozen=True)
class Adapter:
    name: str
    version: str
    detect: Callable[[Grid], bool]
    parse: Callable[[Grid], ParsedFile]


@dataclass(frozen=True)
class WorkbookAdapter:
    name: str
    version: str
    detect: Callable[[list[Sheet]], bool]
    parse: Callable[[list[Sheet]], ParsedFile]


ADAPTERS: tuple[Adapter, ...] = tuple(
    Adapter(m.NAME, m.VERSION, m.detect, m.parse)
    for m in (fcboe_classic_2020, fcboe_general_2020, fcboe_wide_2024, fcboe_wide_2025)
)
WORKBOOK_ADAPTERS: tuple[WorkbookAdapter, ...] = tuple(
    WorkbookAdapter(m.NAME, m.VERSION, m.detect, m.parse)
    for m in (fcboe_sheets_2016, fcboe_general_2016)
)


def _unknown(filename: str, head: list[str]) -> UnknownLayoutError:
    return UnknownLayoutError(
        f"{filename}: no adapter recognizes this layout (first headers: {head}). "
        "Add a sample to data/samples/ and write an adapter for it."
    )


def _one[T](hits: list[T], names: list[str], filename: str, head: list[str]) -> T:
    if not hits:
        raise _unknown(filename, head)
    if len(hits) > 1:
        raise AmbiguousLayoutError(f"{filename}: claimed by {names}")
    return hits[0]


def detect_adapter(grid: Grid, filename: str) -> Adapter:
    """The single adapter whose detection rule matches `grid`."""
    hits = [a for a in ADAPTERS if a.detect(grid)]
    head = [str(v) for v in (grid[0][:6] if grid else [])]
    return _one(hits, [a.name for a in hits], filename, head)


def detect_workbook_adapter(sheets: list[Sheet], filename: str) -> WorkbookAdapter:
    hits = [a for a in WORKBOOK_ADAPTERS if a.detect(sheets)]
    return _one(hits, [a.name for a in hits], filename, [s.name for s in sheets])


def parse_file(path: Path) -> ParsedFile:
    """Read `path` and parse it with the one adapter (grid or workbook) that claims it."""
    sheets = read_workbook(path)
    grid = sheets[0].grid if len(sheets) == 1 else None
    grid_hits = [a for a in ADAPTERS if grid is not None and a.detect(grid)]
    book_hits = [a for a in WORKBOOK_ADAPTERS if a.detect(sheets)]
    if len(grid_hits) + len(book_hits) > 1:
        names = [a.name for a in grid_hits] + [a.name for a in book_hits]
        raise AmbiguousLayoutError(f"{path.name}: claimed by {names}")
    if grid_hits and grid is not None:
        return grid_hits[0].parse(grid)
    if book_hits:
        return book_hits[0].parse(sheets)
    head = [str(v) for v in grid[0][:6]] if grid else [s.name for s in sheets]
    raise _unknown(path.name, head)
