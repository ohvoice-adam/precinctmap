"""Format detection: exactly one adapter must claim a file, or ingest stops.

Single-sheet files go to the grid adapters; multi-sheet workbooks go to the workbook adapters,
which see every sheet and its merged cells.
"""

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from precinctmap.ingest.adapters import (
    fcboe_classic_2020,
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
    for m in (fcboe_classic_2020, fcboe_wide_2024, fcboe_wide_2025)
)
WORKBOOK_ADAPTERS: tuple[WorkbookAdapter, ...] = (
    WorkbookAdapter(
        fcboe_sheets_2016.NAME,
        fcboe_sheets_2016.VERSION,
        fcboe_sheets_2016.detect,
        fcboe_sheets_2016.parse,
    ),
)


def _one[T](hits: list[T], names: list[str], filename: str, head: list[str]) -> T:
    if not hits:
        raise UnknownLayoutError(
            f"{filename}: no adapter recognizes this layout (first headers: {head}). "
            "Add a sample to data/samples/ and write an adapter for it."
        )
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
    """Read `path` and parse it with the one adapter that claims it."""
    sheets = read_workbook(path)
    if len(sheets) == 1:
        return detect_adapter(sheets[0].grid, path.name).parse(sheets[0].grid)
    return detect_workbook_adapter(sheets, path.name).parse(sheets)
