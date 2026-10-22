"""Contest headers of the FCBOE "classic" wide export (sample: 2020 primary).

Each choice takes four columns (ABSENTEE, EARLY VOTE, PROVISIONAL, TOTAL; row 4). Row 1 holds
the contest name in merged blocks that repeat along a long contest, row 2 the party, row 3 the
choice. Every contest ends with OVER VOTES and UNDER VOTES, which is what delimits contests:
a Democratic and a Republican contest with the same name sit side by side.

Some names repeat for separate contests (party central committees are elected per ward or
district, and the file does not say which). Those get a suffix built only from facts in the
file: the precincts whose ballots carried the contest.
"""

import re
from collections.abc import Sequence
from dataclasses import dataclass

from precinctmap.ingest.errors import LayoutError
from precinctmap.ingest.fcboe_common import Grid, Header, as_int, cell_str, loc
from precinctmap.ingest.model import NormalizationLog
from precinctmap.ingest.normalize import clean_text

CYCLE = ("ABSENTEE", "EARLY VOTE", "PROVISIONAL", "TOTAL")
FIRST_CHOICE_COLUMN = 40
_WRITE_IN = re.compile(r"^WI (Dem|Rep|Lib|Grn) (.+)$")
_WARD = re.compile(r"^(.*\S)-[A-Z]+$")  # 'COLUMBUS 12-C' -> 'COLUMBUS 12'


@dataclass
class ContestColumns:
    name: str  # cleaned row-1 name (made unique later)
    name_raw: str
    party: str  # row 2: Dem | Rep | Lib | Non
    choices: list[Header]  # one per choice, `column` = its TOTAL column


def _header(grid: Grid, r: int, c: int) -> str:
    return cell_str(grid[r][c]) if c < len(grid[r]) else ""


def _check_cycle(grid: Grid, c: int) -> None:
    got = tuple(_header(grid, 3, c + i).strip() for i in range(4))
    if got != CYCLE:
        raise LayoutError(
            f"columns {c + 1}-{c + 4}: expected {list(CYCLE)} in row 4, found {list(got)}"
        )


def segment(grid: Grid, log: NormalizationLog) -> list[ContestColumns]:
    """Split the choice columns into contests, each ending with OVER VOTES, UNDER VOTES."""
    width = len(grid[0])
    if (width - FIRST_CHOICE_COLUMN) % 4:
        raise LayoutError(f"{width - FIRST_CHOICE_COLUMN} choice columns is not a multiple of 4")
    contests: list[ContestColumns] = []
    current: ContestColumns | None = None
    for c in range(FIRST_CHOICE_COLUMN, width, 4):
        _check_cycle(grid, c)
        raw_name = _header(grid, 0, c)
        if current is None:
            if not raw_name.strip():
                raise LayoutError(f"column {c + 1}: a contest starts without a name in row 1")
            name = clean_text(raw_name, f"header {loc(0, c)}", log)
            current = ContestColumns(name, raw_name, _header(grid, 1, c).strip(), [])
        elif raw_name.strip() and clean_text(raw_name, f"header {loc(0, c)}", log) != current.name:
            raise LayoutError(
                f"column {c + 1}: contest {current.name!r} changes name before its UNDER VOTES"
            )
        label_raw = _header(grid, 2, c)
        label = clean_text(label_raw, f"header {loc(2, c)}", log)
        party = _header(grid, 1, c).strip()
        if party != current.party:
            raise LayoutError(
                f"column {c + 1}: party {party!r} inside {current.party} contest {current.name!r}"
            )
        current.choices.append(
            Header(c + 3, current.name, party, label, current.name_raw, label_raw)
        )
        if label.upper() == "UNDER VOTES":
            if len(current.choices) < 3 or current.choices[-2].h3.upper() != "OVER VOTES":
                raise LayoutError(f"column {c + 1}: UNDER VOTES not preceded by OVER VOTES")
            contests.append(current)
            current = None
    if current is not None:
        raise LayoutError(f"contest {current.name!r} has no closing UNDER VOTES column")
    return contests


def check_parts(grid: Grid, rows: Sequence[int], contests: Sequence[ContestColumns]) -> None:
    """TOTAL must equal ABSENTEE + EARLY VOTE + PROVISIONAL in every row and choice."""
    bad = []
    for r in rows:
        line = grid[r]
        for k in contests:
            for h in k.choices:
                parts = [as_int(line[h.column - i], loc(r, h.column - i)) or 0 for i in (3, 2, 1)]
                if sum(parts) != (as_int(line[h.column], loc(r, h.column)) or 0):
                    bad.append(loc(r, h.column))
    if bad:
        raise LayoutError(
            f"TOTAL is not ABSENTEE + EARLY VOTE + PROVISIONAL at {bad[:5]} ({len(bad)} cells)"
        )


def rename_write_ins(contests: Sequence[ContestColumns], log: NormalizationLog) -> None:
    """'WI Dem Member of County Central Committee' -> '... Committee, write-in' (logged)."""
    for k in contests:
        m = _WRITE_IN.match(k.name)
        if m and m.group(1) == k.party:
            new = f"{m.group(2)}, write-in"
            log.add(
                "write_in_contest_name", f"header {loc(0, k.choices[0].column - 3)}", k.name, new
            )
            k.name = new


def _area(names: list[str]) -> str:
    if len(names) == 1:
        return names[0]
    wards = {m.group(1) if (m := _WARD.match(n)) else n for n in names}
    if len(wards) == 1:
        return f"{wards.pop()}-*"
    return f"{names[0]} and {len(names) - 1} more"


def disambiguate(
    contests: Sequence[ContestColumns], present: dict[int, list[str]], log: NormalizationLog
) -> None:
    """Suffix contests that share (name, party) with the precincts that carried them.

    `present[i]`: names of precincts whose ballots carried contest i (sheet order).
    """
    groups: dict[tuple[str, str], list[int]] = {}
    for i, k in enumerate(contests):
        groups.setdefault((k.name, k.party), []).append(i)
    for (name, party), idx in groups.items():
        if len(idx) < 2:
            continue
        labels = {i: f"{name} ({_area(present[i])})" if present[i] else name for i in idx}
        if len(set(labels.values())) < len(idx):
            labels = {i: f"{labels[i]} [column {contests[i].choices[0].column - 2}]" for i in idx}
        for i in idx:
            where = f"header {loc(0, contests[i].choices[0].column - 3)}"
            log.add("repeated_contest_name", where, f"{name} ({party})", labels[i])
            contests[i].name = labels[i]
