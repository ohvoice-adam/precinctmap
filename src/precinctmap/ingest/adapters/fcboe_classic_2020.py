"""FCBOE "classic" wide export, 2020 vintage (sample: 2020 primary, `2020-Primary-Official-
Results.xlsx`, one sheet of 911 rows x 5,440 columns).

- Four header rows. Row 4 starts PRECINCT NAME, SUBDIVISION, WARD, PRECINCT, then district
  attributes (CONGRESS, SENATE, HOUSE, SCHOOL, FIRE, POLICE; not used: SENATE and HOUSE look
  swapped in the sample) and a blank column 11.
- Turnout, columns 12-40: REGISTERED VOTERS by party (TOTAL, DEMOCRATIC, REPUBLICAN,
  LIBERTARIAN, NONPARTIAN [sic]); then TOTAL / DEMOCRATIC / REPUBLICAN / LIBERTARIAN /
  NONPARTISAN / BLANK BALLOTS CAST, each as ABSENTEE, EARLY VOTE, PROVISIONAL, TOTAL.
- Choices from column 41 in blocks of four; see `_classic_contests`. Only TOTAL is stored; the
  three parts must add up to it.
- Precinct rows have a 3-digit subdivision; the BOE code is subdivision + ward + precinct
  ('010' '01' 'A' -> '01001A'). Other-county rows ('Athens County') have none. After a blank
  row: a 'Total Votes' label row and its county totals, then 'Filtered Totals' (Excel's
  subtotal of visible rows), which must equal them.
- No blank cells: a contest is absent from a precinct's ballot when all its columns are 0.
- No county-number column; the layout is the Franklin County BOE's.
"""

import dataclasses
import re

from precinctmap.ingest.adapters._classic_contests import (
    ContestColumns,
    check_parts,
    disambiguate,
    rename_write_ins,
    segment,
)
from precinctmap.ingest.adapters._fcboe import pseudo_county
from precinctmap.ingest.errors import LayoutError
from precinctmap.ingest.fcboe_common import (
    KNOWN_PARTIES,
    Grid,
    as_int,
    build_contest,
    cell_str,
    emit_results,
    loc,
    zero_means_absent,
)
from precinctmap.ingest.fcboe_tally import MetaColumn, emit_out_of_county, emit_turnout, reconcile
from precinctmap.ingest.model import ContestSpec, NormalizationLog, ParsedFile, PrecinctRow
from precinctmap.ingest.normalize import precinct_name

NAME = "fcboe_classic_2020"
VERSION = "1"
COUNTY = "Franklin"
ID_COLUMNS = ("PRECINCT NAME", "SUBDIVISION", "WARD", "PRECINCT")
_REGISTERED = ("TOTAL", "DEMOCRATIC", "REPUBLICAN", "LIBERTARIAN", "NONPARTIAN")
_PARTIES = ("ALL", "Dem", "Rep", "Lib", "Non")
_BALLOTS = (  # row-1 name at the first of four columns; the TOTAL is the fourth
    ("TOTAL BALLOTS CAST", "ALL", "ballots_cast"),
    ("DEMOCRATIC BALLOTS CAST", "Dem", "ballots_cast"),
    ("REPUBLICAN BALLOTS CAST", "Rep", "ballots_cast"),
    ("LIBERTARIAN BALLOTS CAST", "Lib", "ballots_cast"),
    ("NONPARTISAN BALLOTS CAST", "Non", "ballots_cast"),
    ("BLANK BALLOTS CAST", "ALL", "ballots_blank"),
)
_TRAILER_LABELS = ("Total Votes", "Filtered Totals")
_SUBDIVISION, _WARD, _PRECINCT = (
    re.compile(r"\d{3}"),
    re.compile(r"\d{2}"),
    re.compile(r"[A-Z]{1,2}"),
)


def _cell(grid: Grid, r: int, c: int) -> str:
    return cell_str(grid[r][c]).strip() if r < len(grid) and c < len(grid[r]) else ""


def detect(grid: Grid) -> bool:
    return (
        len(grid) > 4
        and tuple(_cell(grid, 3, c) for c in range(4)) == ID_COLUMNS
        and _cell(grid, 2, 11) == "REGISTERED VOTERS"
        and _cell(grid, 3, 40) == "ABSENTEE"
    )


def meta_columns(grid: Grid) -> list[MetaColumn]:
    """Turnout columns, checked label by label."""
    meta = []
    for i, (label, party) in enumerate(zip(_REGISTERED, _PARTIES, strict=True)):
        if _cell(grid, 3, 11 + i) != label:
            raise LayoutError(f"column {12 + i}: expected registered-voters {label!r} in row 4")
        meta.append(MetaColumn(11 + i, f"REGISTERED VOTERS {label}", party, "registered"))
    for j, (label, party, field) in enumerate(_BALLOTS):
        c = 16 + 4 * j
        if _cell(grid, 0, c) != label or _cell(grid, 3, c + 3) != "TOTAL":
            raise LayoutError(f"column {c + 1}: expected {label!r} with a TOTAL in column {c + 4}")
        meta.append(MetaColumn(c + 3, label, party, field))  # type: ignore[arg-type]
    return meta


def _check_meta_parts(grid: Grid, rows: list[int]) -> None:
    for r in rows:
        for j in range(len(_BALLOTS)):
            c = 16 + 4 * j
            parts = sum(as_int(grid[r][c + i], loc(r, c + i)) or 0 for i in range(3))
            if parts != (as_int(grid[r][c + 3], loc(r, c + 3)) or 0):
                raise LayoutError(f"{loc(r, c + 3)}: ballots TOTAL is not the sum of its parts")


def _blank(grid: Grid, r: int) -> bool:
    return not any(cell_str(v).strip() for v in grid[r])


def _trailer(grid: Grid, end: int) -> dict[str, int]:
    """After the data block: label rows (one text cell) each followed by its row of totals."""
    rows = [r for r in range(end, len(grid)) if not _blank(grid, r)]
    out: dict[str, int] = {}
    for label_row, values_row in zip(rows[::2], rows[1::2], strict=False):
        cells = [cell_str(v).strip() for v in grid[label_row] if cell_str(v).strip()]
        if len(cells) != 1 or cells[0] not in _TRAILER_LABELS:
            raise LayoutError(
                f"row {label_row + 1}: expected one of {_TRAILER_LABELS}, found {cells[:3]}"
            )
        out[cells[0]] = values_row
    if len(rows) % 2 or "Total Votes" not in out:
        raise LayoutError("expected a 'Total Votes' label row followed by the county-total row")
    return out


def split_rows(grid: Grid) -> tuple[list[int], int]:
    """Data rows (row 5 to the first blank row) and the 'Total Votes' row after them. A
    'Filtered Totals' row (Excel's subtotal of the visible rows) must equal it."""
    end = next((r for r in range(4, len(grid)) if _blank(grid, r)), len(grid))
    data = list(range(4, end))
    if not data:
        raise LayoutError("no data rows")
    trailer = _trailer(grid, end)
    total = trailer["Total Votes"]
    filtered = trailer.get("Filtered Totals")
    if filtered is not None and [cell_str(v) for v in grid[filtered]] != [
        cell_str(v) for v in grid[total]
    ]:
        raise LayoutError(
            f"rows {total + 1} and {filtered + 1}: Total Votes and Filtered Totals differ"
        )
    return data, total


def _ward(grid: Grid, r: int, log: NormalizationLog) -> str:
    """Two-digit ward. Township precincts have none: the cell holds the number 0, which the
    BOE's precinct codes write as '00' (BLENDON-A = '03000A')."""
    raw = grid[r][2]
    if isinstance(raw, int | float) and not isinstance(raw, bool):
        n = as_int(raw, loc(r, 2))
        if n is None or n > 99:
            raise LayoutError(f"{loc(r, 2)}: ward {raw!r} is not a 2-digit number")
        log.add("ward_number", f"ward {loc(r, 2)}", str(raw), f"{n:02d}")
        return f"{n:02d}"
    return cell_str(raw).strip()


def classify_row(grid: Grid, r: int, log: NormalizationLog) -> PrecinctRow | str:
    name, sub, pct = _cell(grid, r, 0), _cell(grid, r, 1), _cell(grid, r, 3)
    ward = _ward(grid, r, log) if sub else _cell(grid, r, 2)
    if not sub:
        if as_int(grid[r][11], loc(r, 11)):
            raise LayoutError(f"row {r + 1}: out-of-county row {name!r} has registered voters")
        return pseudo_county(name, f"row {r + 1}")
    if not (_SUBDIVISION.fullmatch(sub) and _WARD.fullmatch(ward) and _PRECINCT.fullmatch(pct)):
        raise LayoutError(
            f"row {r + 1}: precinct code parts {sub!r} {ward!r} {pct!r} are malformed"
        )
    if not name:
        raise LayoutError(f"row {r + 1}: blank precinct name")
    return PrecinctRow(
        r + 1, f"{sub}{ward}{pct}", name, precinct_name(name, f"precinct {loc(r, 0)}", log)
    )


def _contests(
    grid: Grid, cols: list[ContestColumns], keyed: list[tuple[int, str]], log: NormalizationLog
) -> list[ContestSpec]:
    rename_write_ins(cols, log)
    present = {
        i: [
            name
            for r, name in keyed
            if any(as_int(grid[r][h.column], loc(r, h.column)) for h in k.choices)
        ]
        for i, k in enumerate(cols)
    }
    disambiguate(cols, present, log)
    out = []
    for i, k in enumerate(cols):
        run = [dataclasses.replace(h, h1=k.name) for h in k.choices]
        spec = build_contest(i, run, log)
        out.append(dataclasses.replace(spec, party=k.party if k.party in KNOWN_PARTIES else None))
    return out


def parse(grid: Grid) -> ParsedFile:
    log = NormalizationLog()
    meta = meta_columns(grid)
    data, total_idx = split_rows(grid)
    real: list[tuple[int, PrecinctRow]] = []
    pseudo: list[tuple[int, str]] = []
    for r in data:
        kind = classify_row(grid, r, log)
        (pseudo.append((r, kind)) if isinstance(kind, str) else real.append((r, kind)))
    names = [p.name for _, p in real]
    if len(set(names)) != len(names):
        raise LayoutError(
            f"duplicate precinct names: {sorted({n for n in names if names.count(n) > 1})}"
        )
    keyed = [(r, p.name) for r, p in real]
    _check_meta_parts(grid, [*data, total_idx])
    cols = segment(grid, log)
    check_parts(grid, [*data, total_idx], cols)
    contests = _contests(grid, cols, keyed, log)
    results, absent = emit_results(grid, keyed, contests, zero_means_absent)
    columns = [(m.column, m.label) for m in meta] + [
        (ch.column, f"{c.name_display} | {ch.name_display}") for c in contests for ch in c.choices
    ]
    return ParsedFile(
        adapter=NAME,
        adapter_version=VERSION,
        county=COUNTY,
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
        has_over_under=True,
        normalizations=log,
    )
