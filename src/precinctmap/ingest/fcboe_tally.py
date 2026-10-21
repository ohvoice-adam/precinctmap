"""Turnout, out-of-county rows, and county-total reconciliation for the FCBOE wide exports."""

from collections.abc import Sequence
from dataclasses import dataclass

from precinctmap.ingest.fcboe_common import Grid, as_int, loc
from precinctmap.ingest.model import (
    ColumnCheck,
    ContestSpec,
    OutOfCountyRow,
    TurnoutField,
    TurnoutRow,
)


@dataclass(frozen=True)
class MetaColumn:
    """A turnout column: which party it counts and which field."""

    column: int
    label: str
    party: str  # "ALL" or a party code
    field: TurnoutField


def emit_turnout(
    grid: Grid, precincts: Sequence[tuple[int, str]], meta: Sequence[MetaColumn]
) -> list[TurnoutRow]:
    """One TurnoutRow per (precinct, party) present in the meta columns."""
    parties = list(dict.fromkeys(m.party for m in meta))
    out = []
    for r, name in precincts:
        for party in parties:
            values: dict[str, int | None] = {}
            for m in meta:
                if m.party == party:
                    values[m.field] = as_int(grid[r][m.column], loc(r, m.column))
            out.append(
                TurnoutRow(
                    name,
                    party,
                    values.get("registered"),
                    values.get("ballots_cast"),
                    values.get("ballots_blank"),
                )
            )
    return out


def emit_out_of_county(
    grid: Grid, pseudo: Sequence[tuple[int, str]], contests: Sequence[ContestSpec]
) -> list[OutOfCountyRow]:
    """Nonzero votes on out-of-county pseudo-rows (other counties' share of joint contests)."""
    out = []
    for r, county in pseudo:
        for c in contests:
            for ch in c.choices:
                v = as_int(grid[r][ch.column], loc(r, ch.column))
                if v:
                    out.append(OutOfCountyRow(county, c.ordinal, ch.ordinal, v))
    return out


def reconcile(
    grid: Grid,
    real_rows: Sequence[int],
    pseudo_rows: Sequence[int],
    total_idx: int,
    columns: Sequence[tuple[int, str]],
) -> list[ColumnCheck]:
    """Per column: precinct sum + out-of-county sum vs the ZZZ row. Blanks count as 0."""

    def col_sum(rows: Sequence[int], c: int) -> int:
        return sum(as_int(grid[r][c], loc(r, c)) or 0 for r in rows)

    return [
        ColumnCheck(
            column=c,
            label=label,
            precinct_sum=col_sum(real_rows, c),
            out_of_county_sum=col_sum(pseudo_rows, c),
            county_total=as_int(grid[total_idx][c], loc(total_idx, c)) or 0,
        )
        for c, label in columns
    ]
