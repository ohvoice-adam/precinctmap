"""Contest headers of the FCBOE "classic" wide exports (samples: 2020 primary, 2020 general).

Each choice takes a fixed run of vote-type columns ending in TOTAL (2020 primary: ABSENTEE,
EARLY VOTE, PROVISIONAL, TOTAL in row 4; 2020 general adds Election Day, in row 5). One header
row holds the contest name in merged blocks that repeat along a long contest, one the party,
one the choice; `ChoiceLayout` says which. Every contest ends with OVER VOTES and UNDER VOTES,
which is what delimits contests: a Democratic and a Republican contest with the same name sit
side by side.

Some names repeat for separate contests (party central committees are elected per ward or
district, and the file does not say which). Those get a suffix built only from facts in the
file: the precincts whose ballots carried the contest.
"""

import dataclasses
import re
from collections.abc import Sequence
from dataclasses import dataclass

from precinctmap.ingest.errors import LayoutError
from precinctmap.ingest.fcboe_common import Grid, Header, as_int, cell_str, loc
from precinctmap.ingest.model import NormalizationLog
from precinctmap.ingest.normalize import clean_text


@dataclass(frozen=True)
class ChoiceLayout:
    first_column: int  # 0-based column of the first choice
    cycle: tuple[str, ...]  # vote-type labels per choice; the last is the TOTAL
    name_row: int
    party_row: int
    label_row: int
    cycle_row: int


PRIMARY_2020 = ChoiceLayout(40, ("ABSENTEE", "EARLY VOTE", "PROVISIONAL", "TOTAL"), 0, 1, 2, 3)
GENERAL_2020 = ChoiceLayout(
    38, ("Absentee", "Early Vote", "Election Day", "Provisoinal", "TOTAL"), 0, 2, 1, 4
)  # 'Provisoinal' [sic], as in the file
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


def _check_cycle(grid: Grid, c: int, layout: ChoiceLayout) -> None:
    n = len(layout.cycle)
    got = tuple(_header(grid, layout.cycle_row, c + i).strip() for i in range(n))
    if got != layout.cycle:
        raise LayoutError(
            f"columns {c + 1}-{c + n}: expected {list(layout.cycle)} in row"
            f" {layout.cycle_row + 1}, found {list(got)}"
        )


def _same_contest(
    current: ContestColumns, name: str, c: int, where: str, log: NormalizationLog
) -> None:
    """A name block inside one contest (before its UNDER VOTES) must repeat the contest's name.

    One exception, logged: a block that only adds to the name (2020 general: 'State Board of
    Education' then 'State Board of Education 6th' for one race) gives the fuller name.
    """
    if name == current.name or current.name.startswith(name):
        return
    if name.startswith(current.name):
        log.add("contest_name_completed", where, current.name, name)
        current.name = name
        return
    raise LayoutError(
        f"column {c + 1}: contest {current.name!r} changes name to {name!r} before its UNDER VOTES"
    )


def segment(
    grid: Grid, log: NormalizationLog, layout: ChoiceLayout = PRIMARY_2020
) -> list[ContestColumns]:
    """Split the choice columns into contests, each ending with OVER VOTES, UNDER VOTES."""
    width, n, first = len(grid[0]), len(layout.cycle), layout.first_column
    if (width - first) % n:
        raise LayoutError(f"{width - first} choice columns is not a multiple of {n}")
    contests: list[ContestColumns] = []
    current: ContestColumns | None = None
    for c in range(first, width, n):
        _check_cycle(grid, c, layout)
        raw_name = _header(grid, layout.name_row, c)
        where = f"header {loc(layout.name_row, c)}"
        if current is None:
            if not raw_name.strip():
                raise LayoutError(f"column {c + 1}: a contest starts without a name")
            name = clean_text(raw_name, where, log)
            current = ContestColumns(name, raw_name, _header(grid, layout.party_row, c).strip(), [])
        elif raw_name.strip():
            _same_contest(current, clean_text(raw_name, where, log), c, where, log)
        label_raw = _header(grid, layout.label_row, c)
        label = clean_text(label_raw, f"header {loc(layout.label_row, c)}", log)
        party = _header(grid, layout.party_row, c).strip()
        if party != current.party:
            raise LayoutError(
                f"column {c + 1}: party {party!r} inside {current.party} contest {current.name!r}"
            )
        current.choices.append(
            Header(c + n - 1, current.name, party, label, current.name_raw, label_raw)
        )
        if label.upper() == "UNDER VOTES":
            if len(current.choices) < 3 or current.choices[-2].h3.upper() != "OVER VOTES":
                raise LayoutError(f"column {c + 1}: UNDER VOTES not preceded by OVER VOTES")
            current.choices = [dataclasses.replace(h, h1=current.name) for h in current.choices]
            contests.append(current)
            current = None
    if current is not None:
        raise LayoutError(f"contest {current.name!r} has no closing UNDER VOTES column")
    return contests


def check_parts(
    grid: Grid,
    rows: Sequence[int],
    contests: Sequence[ContestColumns],
    layout: ChoiceLayout = PRIMARY_2020,
) -> None:
    """TOTAL must equal the sum of the vote-type columns before it, in every row and choice."""
    offsets = range(len(layout.cycle) - 1, 0, -1)
    parts_label = " + ".join(layout.cycle[:-1])
    bad = []
    for r in rows:
        line = grid[r]
        for k in contests:
            for h in k.choices:
                parts = [as_int(line[h.column - i], loc(r, h.column - i)) or 0 for i in offsets]
                if sum(parts) != (as_int(line[h.column], loc(r, h.column)) or 0):
                    bad.append(loc(r, h.column))
    if bad:
        raise LayoutError(f"TOTAL is not {parts_label} at {bad[:5]} ({len(bad)} cells)")


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
