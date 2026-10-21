"""Review checks: long-format reconciliation and precinct match against the boundary set."""

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date

import duckdb

from precinctmap.ingest.model import ParsedFile
from precinctmap.registry.store import feature_ids, set_for


@dataclass(frozen=True)
class LongFormatCheck:
    """Stored long rows + out-of-county rows must equal the ZZZ total for every choice."""

    choices: int
    result_rows: int
    failures: list[str]

    @property
    def ok(self) -> bool:
        return not self.failures


@dataclass
class BoundaryMatch:
    boundary_set_id: str | None
    retroactive: bool = False
    results_precincts: int = 0
    matched: int = 0
    results_only: list[str] = field(default_factory=list)
    boundary_only: list[str] = field(default_factory=list)

    @property
    def rate(self) -> float | None:
        return self.matched / self.results_precincts if self.results_precincts else None


def long_format_check(parsed: ParsedFile) -> LongFormatCheck:
    """Re-total the long tables per choice and compare with the county-total row.

    Proves no vote was lost turning the wide sheet into rows (absent cells must be zeros).
    """
    totals = {c.column: c.county_total for c in parsed.column_checks}
    summed: dict[tuple[int, int], int] = defaultdict(int)
    for r in parsed.results:
        summed[(r.contest_ordinal, r.choice_ordinal)] += r.votes
    for o in parsed.out_of_county:
        summed[(o.contest_ordinal, o.choice_ordinal)] += o.votes
    failures = []
    n = 0
    for c in parsed.contests:
        for ch in c.choices:
            n += 1
            got, want = summed.get((c.ordinal, ch.ordinal), 0), totals[ch.column]
            if got != want:
                failures.append(f"{c.name_display} | {ch.name_display}: rows {got} != total {want}")
    return LongFormatCheck(n, len(parsed.results), failures)


def boundary_match(
    con: duckdb.DuckDBPyConnection, parsed: ParsedFile, election_date: date | None
) -> BoundaryMatch:
    """Match result precinct names to the precinct boundary set valid on `election_date`."""
    if election_date is None:
        return BoundaryMatch(None)
    ref = set_for(con, "precinct", parsed.county, election_date)
    if ref is None:
        return BoundaryMatch(None)
    names = {p.name for p in parsed.precincts}
    features = feature_ids(con, ref.boundary_set_id)
    return BoundaryMatch(
        boundary_set_id=ref.boundary_set_id,
        retroactive=ref.retroactive,
        results_precincts=len(names),
        matched=len(names & features),
        results_only=sorted(names - features),
        boundary_only=sorted(features - names),
    )
