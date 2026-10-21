"""Adapter-independent representation of one parsed results file.

Ordinals refer to positions in the source sheet so every stored value traces back to a cell.
"""

from dataclasses import dataclass, field
from typing import Literal

ChoiceKind = Literal[
    "candidate", "yes", "no", "write_in", "withdrawn", "no_petition", "over", "under"
]
ContestType = Literal["candidate", "issue"]
TurnoutField = Literal["registered", "ballots_cast", "ballots_blank"]

#: Kinds excluded from share denominators.
NON_VOTE_KINDS: frozenset[str] = frozenset({"over", "under"})


@dataclass(frozen=True)
class Normalization:
    """One logged change to source text (rule 6: log every normalization)."""

    kind: str
    location: str
    before: str
    after: str


@dataclass
class NormalizationLog:
    entries: list[Normalization] = field(default_factory=list)

    def add(self, kind: str, location: str, before: str, after: str) -> None:
        self.entries.append(Normalization(kind, location, before, after))


@dataclass(frozen=True)
class ChoiceSpec:
    column: int  # 0-based sheet column
    ordinal: int  # position within the contest
    name_raw: str
    name_display: str
    party: str | None
    kind: ChoiceKind


@dataclass(frozen=True)
class ContestSpec:
    ordinal: int  # position among contests in the sheet
    name_raw: str
    name_display: str
    party: str | None  # primary ballot party; None for nonpartisan or general
    contest_type: ContestType
    jurisdiction: str | None
    choices: tuple[ChoiceSpec, ...]


@dataclass(frozen=True)
class PrecinctRow:
    source_row: int  # 1-based sheet row
    code_raw: str
    name_raw: str
    name: str  # normalized key (ward padded)


@dataclass(frozen=True)
class ResultRow:
    precinct_name: str
    contest_ordinal: int
    choice_ordinal: int
    votes: int


@dataclass(frozen=True)
class TurnoutRow:
    precinct_name: str
    party: str  # "ALL" for totals, else the sheet's party code
    registered: int | None
    ballots_cast: int | None
    ballots_blank: int | None


@dataclass(frozen=True)
class OutOfCountyRow:
    county_name: str
    contest_ordinal: int
    choice_ordinal: int
    votes: int


@dataclass(frozen=True)
class ColumnCheck:
    """Source column reconciled against the county-total row."""

    column: int
    label: str
    precinct_sum: int
    out_of_county_sum: int
    county_total: int

    @property
    def ok(self) -> bool:
        return self.precinct_sum + self.out_of_county_sum == self.county_total


@dataclass
class ParsedFile:
    adapter: str
    adapter_version: str
    county: str
    contests: list[ContestSpec]
    precincts: list[PrecinctRow]
    results: list[ResultRow]
    turnout: list[TurnoutRow]
    out_of_county: list[OutOfCountyRow]
    out_of_county_names: list[str]
    column_checks: list[ColumnCheck]
    absent_cells: int  # precinct x contest cells treated as "not on this ballot"
    has_over_under: bool
    normalizations: NormalizationLog
