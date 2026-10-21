"""Format detection: exactly one adapter must claim a file, or ingest stops."""

from collections.abc import Callable
from dataclasses import dataclass

from precinctmap.ingest.adapters import fcboe_wide_2024, fcboe_wide_2025
from precinctmap.ingest.errors import AmbiguousLayoutError, UnknownLayoutError
from precinctmap.ingest.fcboe_common import Grid
from precinctmap.ingest.model import ParsedFile


@dataclass(frozen=True)
class Adapter:
    name: str
    version: str
    detect: Callable[[Grid], bool]
    parse: Callable[[Grid], ParsedFile]


ADAPTERS: tuple[Adapter, ...] = tuple(
    Adapter(m.NAME, m.VERSION, m.detect, m.parse) for m in (fcboe_wide_2024, fcboe_wide_2025)
)


def detect_adapter(grid: Grid, filename: str) -> Adapter:
    """The single adapter whose detection rule matches `grid`."""
    hits = [a for a in ADAPTERS if a.detect(grid)]
    if not hits:
        head = [str(v) for v in (grid[0][:6] if grid else [])]
        raise UnknownLayoutError(
            f"{filename}: no adapter recognizes this layout (first headers: {head}). "
            "Add a sample to data/samples/ and write an adapter for it."
        )
    if len(hits) > 1:
        raise AmbiguousLayoutError(f"{filename}: claimed by {[a.name for a in hits]}")
    return hits[0]
