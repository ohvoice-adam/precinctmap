"""Shared parse flow for FCBOE wide exports; each adapter version supplies its LayoutRules."""

import re
from collections.abc import Callable
from dataclasses import dataclass

from precinctmap.ingest.errors import LayoutError
from precinctmap.ingest.fcboe_common import (
    Grid,
    Header,
    PresencePolicy,
    build_contest,
    cell_str,
    contest_runs,
    county_name,
    emit_results,
    read_headers,
    total_row_index,
)
from precinctmap.ingest.fcboe_tally import MetaColumn, emit_out_of_county, emit_turnout, reconcile
from precinctmap.ingest.model import NormalizationLog, ParsedFile, PrecinctRow

ID_COLUMNS = ("COUNTY NUMBER", "PRECINCT CODE", "PRECINCT NAME")
_COUNTY_ROW_NAME = re.compile(r"[A-Z][a-z]+(?: [A-Z][a-z]+)*(?: County)?")

#: Returns a PrecinctRow for a real precinct, or the county name for an out-of-county pseudo-row.
RowClassifier = Callable[[Grid, int, NormalizationLog], PrecinctRow | str]


@dataclass(frozen=True)
class LayoutRules:
    name: str
    version: str
    meta_columns: Callable[[list[Header]], list[MetaColumn]]
    classify_row: RowClassifier
    presence: PresencePolicy
    has_over_under: bool


def first_row(grid: Grid) -> list[str]:
    return [cell_str(v).strip() for v in grid[0]] if grid else []


def pseudo_county(raw_name: str, where: str) -> str:
    """'Delaware County' or bare 'Delaware' -> 'Delaware County'; anything else raises."""
    name = raw_name.strip()
    if not _COUNTY_ROW_NAME.fullmatch(name):
        raise LayoutError(f"{where}: out-of-county row has unexpected name {raw_name!r}")
    return name if name.endswith(" County") else f"{name} County"


def parse_with(rules: LayoutRules, grid: Grid) -> ParsedFile:
    log = NormalizationLog()
    headers = read_headers(grid, log)
    if [h.h1 for h in headers[:3]] != list(ID_COLUMNS):
        raise LayoutError(f"first three headers are not {ID_COLUMNS}")
    total_idx = total_row_index(grid)
    county = county_name(grid, total_idx)
    meta = rules.meta_columns(headers)
    start = 3 + len(meta)
    contests = [build_contest(i, run, log) for i, run in enumerate(contest_runs(headers[start:]))]
    real, pseudo = _classify_rows(rules, grid, total_idx, log)
    keyed = [(r, p.name) for r, p in real]
    results, absent = emit_results(grid, keyed, contests, rules.presence)
    columns = [(m.column, m.label) for m in meta] + [
        (ch.column, f"{c.name_display} | {ch.name_display}") for c in contests for ch in c.choices
    ]
    return ParsedFile(
        adapter=rules.name,
        adapter_version=rules.version,
        county=county,
        contests=contests,
        precincts=[p for _, p in real],
        results=results,
        turnout=emit_turnout(grid, keyed, meta),
        out_of_county=emit_out_of_county(grid, pseudo, contests),
        out_of_county_names=[name for _, name in pseudo],
        column_checks=reconcile(
            grid, [r for r, _ in real], [r for r, _ in pseudo], total_idx, columns
        ),
        absent_cells=absent,
        has_over_under=rules.has_over_under,
        normalizations=log,
    )


def _classify_rows(
    rules: LayoutRules, grid: Grid, total_idx: int, log: NormalizationLog
) -> tuple[list[tuple[int, PrecinctRow]], list[tuple[int, str]]]:
    real: list[tuple[int, PrecinctRow]] = []
    pseudo: list[tuple[int, str]] = []
    for r in range(3, total_idx):
        if not any(cell_str(v).strip() for v in grid[r]):
            raise LayoutError(f"row {r + 1}: blank row inside the data block")
        kind = rules.classify_row(grid, r, log)
        if isinstance(kind, str):
            pseudo.append((r, kind))
        else:
            real.append((r, kind))
    if not real:
        raise LayoutError("no precinct rows found")
    names = [p.name for _, p in real]
    dupes = sorted({n for n in names if names.count(n) > 1})
    if dupes:
        raise LayoutError(f"duplicate precinct names after normalization: {dupes}")
    return real, pseudo
