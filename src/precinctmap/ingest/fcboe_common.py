"""Building blocks shared by the Franklin County BOE wide-export adapters.

Both layouts put contest names in sheet row 1, party codes in row 2, choice labels in row 3,
one precinct per row after that, and a `ZZZ` / `COUNTY TOTALS` row last. Layout-specific
rules (turnout columns, pseudo-row detection, blank-cell meaning) live in each adapter.
"""

import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from precinctmap.ingest.corrections import CHOICE_FIXES, CONTEST_FIXES, apply_fixes
from precinctmap.ingest.errors import LayoutError
from precinctmap.ingest.model import (
    ChoiceKind,
    ChoiceSpec,
    ContestSpec,
    ContestType,
    NormalizationLog,
    ResultRow,
)
from precinctmap.ingest.normalize import clean_text, strip_trailing_dash

Grid = list[list[object]]
#: Decides whether a contest was on a precinct's ballot from its raw cell values.
PresencePolicy = Callable[[list[int | None], str], bool]

COUNTY_NUMBERS = {25: "Franklin"}
KNOWN_PARTIES = frozenset({"Dem", "Rep", "Lib", "Grn", "Npc", "OPC"})
NONPARTISAN = "Non"
TOTAL_CODE = "ZZZ"

_MUNICIPAL = re.compile(
    r"((?:City|Village|Township) of [A-Z][A-Za-z .'-]*?)(?: Council Ward \d+)?$"
)
_SCHOOL = re.compile(r" ((?:City|Local|Exempted Village) School District)$")
# Words that end a school district's name when walking backward from "School District".
_NOT_NAME = frozenset(
    {
        "Bond",
        "Board",
        "District",
        "Education",
        "For",
        "Income",
        "Issue",
        "Levy",
        "Member",
        "of",
        "Proposed",
        "Tax",
        "the",
    }
)


@dataclass(frozen=True)
class Header:
    column: int
    h1: str  # cleaned contest / meta name
    h2: str  # party code or ''
    h3: str  # choice label or meta marker
    h1_raw: str
    h3_raw: str


def loc(row: int, col: int) -> str:
    """1-based sheet location, e.g. 'r4c12'."""
    return f"r{row + 1}c{col + 1}"


def cell_str(value: object) -> str:
    return "" if value is None else str(value)


def as_int(value: object, where: str) -> int | None:
    """Vote/turnout cell -> int; '' -> None. Non-integers raise LayoutError."""
    if value == "" or value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise LayoutError(f"{where}: expected a count, found {value!r}")
    if float(value) != int(value) or value < 0:
        raise LayoutError(f"{where}: expected a non-negative whole count, found {value!r}")
    return int(value)


def read_headers(grid: Grid, log: NormalizationLog) -> list[Header]:
    if len(grid) < 4:
        raise LayoutError("sheet has fewer than 4 rows; expected 3 header rows plus data")
    width = len(grid[0])
    out = []
    for c in range(width):
        raw = [cell_str(grid[r][c]) if c < len(grid[r]) else "" for r in range(3)]
        h1 = clean_text(raw[0], f"header {loc(0, c)}", log)
        h2 = clean_text(raw[1], f"header {loc(1, c)}", log)
        h3 = clean_text(raw[2], f"header {loc(2, c)}", log)
        out.append(Header(c, h1, h2, h3, raw[0], raw[2]))
    return out


def total_row_index(grid: Grid) -> int:
    """Index of the `ZZZ` county-total row, which must be the last non-empty row."""
    rows = [i for i in range(3, len(grid)) if any(cell_str(v).strip() for v in grid[i])]
    if not rows:
        raise LayoutError("no data rows")
    last = rows[-1]
    if cell_str(grid[last][1]) != TOTAL_CODE:
        raise LayoutError(f"last row {last + 1} is not the {TOTAL_CODE} county-total row")
    if sum(1 for i in rows if cell_str(grid[i][1]) == TOTAL_CODE) != 1:
        raise LayoutError(f"expected exactly one {TOTAL_CODE} row")
    return last


def county_name(grid: Grid, total_idx: int) -> str:
    numbers = {as_int(grid[r][0], loc(r, 0)) for r in range(3, total_idx + 1)}
    if len(numbers) != 1:
        raise LayoutError(f"mixed COUNTY NUMBER values: {sorted(map(str, numbers))}")
    number = numbers.pop()
    if number not in COUNTY_NUMBERS:
        raise LayoutError(f"COUNTY NUMBER {number} is not supported (only Franklin = 25)")
    return COUNTY_NUMBERS[number]


def contest_runs(headers: Sequence[Header]) -> list[list[Header]]:
    """Group contest columns into contiguous runs of the same row-1 name."""
    runs: list[list[Header]] = []
    for h in headers:
        if runs and runs[-1][0].h1 == h.h1:
            runs[-1].append(h)
        else:
            runs.append([h])
    seen: set[str] = set()
    for run in runs:
        name = run[0].h1
        if not name:
            raise LayoutError(f"column {run[0].column + 1}: blank contest name")
        if name in seen:
            raise LayoutError(f"contest {name!r} appears in non-adjacent column runs")
        seen.add(name)
    return runs


def split_party_prefix(text: str) -> tuple[str | None, str]:
    head, _, rest = text.partition(" ")
    return (head, rest) if head in KNOWN_PARTIES and rest else (None, text)


def choice_kind(label: str) -> ChoiceKind:
    u = label.upper()
    fixed: dict[str, ChoiceKind] = {
        "OVER VOTES": "over",
        "UNDER VOTES": "under",
        "WRITE-IN": "write_in",
        "CANDIDATE WITHDRAWN": "withdrawn",
        "NO VALID PETITION FILED": "no_petition",
        "NO OTHER VALID PETITION FILED": "no_petition",
        "YES": "yes",
        "NO": "no",
    }
    if u in fixed:
        return fixed[u]
    if u.startswith("FOR THE "):
        return "yes"
    if u.startswith("AGAINST THE "):
        return "no"
    return "candidate"


def jurisdiction(name: str) -> str | None:
    """'... City of Hilliard Council Ward 2' -> 'City of Hilliard'; school districts by name.

    School district names are the capitalized words just before 'City/Local School District'
    ('Proposed Income Tax Pickerington Local School District' -> 'Pickerington Local ...').
    """
    m = _MUNICIPAL.search(name)
    if m:
        return m.group(1)
    s = _SCHOOL.search(name)
    if not s:
        return None
    words = name[: s.start()].split(" ")
    kept: list[str] = []
    for w in reversed(words):
        if not w or not w[0].isupper() or w in _NOT_NAME:
            break
        kept.insert(0, w)
    return " ".join([*kept, s.group(1)]) if kept else None


def build_contest(ordinal: int, run: list[Header], log: NormalizationLog) -> ContestSpec:
    """Turn one column run into a ContestSpec, splitting party prefixes and choice kinds."""
    first = run[0]
    party, display = split_party_prefix(first.h1)
    if party and any(h.h2 != party for h in run):
        raise LayoutError(f"contest {first.h1!r}: party prefix {party} disagrees with row 2")
    where = f"contest {loc(0, first.column)}"
    display = apply_fixes(strip_trailing_dash(display, where, log), CONTEST_FIXES, where, log)
    choices = [_build_choice(i, h, log) for i, h in enumerate(run)]
    kinds = {c.kind for c in choices} - {"over", "under"}
    contest_type: ContestType = "issue" if kinds and kinds <= {"yes", "no"} else "candidate"
    return ContestSpec(
        ordinal=ordinal,
        name_raw=first.h1_raw,
        name_display=display,
        party=party,
        contest_type=contest_type,
        jurisdiction=jurisdiction(display),
        choices=tuple(choices),
    )


def _build_choice(ordinal: int, h: Header, log: NormalizationLog) -> ChoiceSpec:
    if not h.h3:
        raise LayoutError(f"column {h.column + 1} ({h.h1!r}): blank choice label in row 3")
    if h.h2 and h.h2 != NONPARTISAN and h.h2 not in KNOWN_PARTIES:
        raise LayoutError(f"column {h.column + 1}: unknown party code {h.h2!r} in row 2")
    label_party, name = split_party_prefix(h.h3)
    if label_party and h.h2 not in ("", NONPARTISAN, label_party):
        raise LayoutError(f"column {h.column + 1}: label party {label_party} vs row 2 {h.h2}")
    party = label_party or (h.h2 if h.h2 in KNOWN_PARTIES else None)
    name = apply_fixes(name, CHOICE_FIXES, f"choice {loc(2, h.column)}", log)
    return ChoiceSpec(h.column, ordinal, h.h3_raw, name, party, choice_kind(name))


def blank_means_absent(values: list[int | None], where: str) -> bool:
    """2024 layout: a contest not on a precinct's ballot is blank in every column."""
    blanks = sum(v is None for v in values)
    if blanks and blanks != len(values):
        raise LayoutError(f"{where}: contest is partly blank in this precinct")
    return blanks == 0


def zero_means_absent(values: list[int | None], where: str) -> bool:
    """2025 layout: no blanks; a contest is absent when every column, under-votes included, is 0."""
    if any(v is None for v in values):
        raise LayoutError(f"{where}: unexpected blank cell")
    return sum(v or 0 for v in values) > 0


def emit_results(
    grid: Grid,
    precincts: Sequence[tuple[int, str]],
    contests: Sequence[ContestSpec],
    present: PresencePolicy,
) -> tuple[list[ResultRow], int]:
    """Long rows for every (precinct, contest) on the ballot; returns (rows, absent cell count)."""
    rows: list[ResultRow] = []
    absent = 0
    for r, name in precincts:
        line = grid[r]
        for c in contests:
            values = [as_int(line[ch.column], loc(r, ch.column)) for ch in c.choices]
            if not present(values, f"{loc(r, c.choices[0].column)} {name} / {c.name_display}"):
                absent += 1
                continue
            rows.extend(
                ResultRow(name, c.ordinal, ch.ordinal, v or 0)
                for ch, v in zip(c.choices, values, strict=True)
            )
    return rows, absent
