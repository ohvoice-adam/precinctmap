"""Reviewed combinations: an extra contest that adds up contests split by district.

The member contests stay as they are; the combined contest is added after them. Its choices
are the members' choices matched by name (in first-seen order), and a precinct's votes are the
sum over the members on its ballot: a precinct split by a district line gives each part its
own district's contest, so summing counts every voter once. Other counties' votes are summed
the same way, and each combined choice gets a county-total check built from its members'.

Add an entry only after reviewing the real file; each application is logged as a
'combined_contest' normalization.
"""

import dataclasses
import re
from collections import defaultdict
from dataclasses import dataclass

from precinctmap.ingest.errors import IngestError
from precinctmap.ingest.model import (
    ChoiceSpec,
    ColumnCheck,
    ContestSpec,
    OutOfCountyRow,
    ParsedFile,
    ResultRow,
)


def combined_sheet(ordinal: int) -> str:
    """ChoiceSpec.sheet of a combined contest's choices (their `column` is the position).

    One per combined contest, so checks keyed by (sheet, column) never collide."""
    return f"(combined contest {ordinal})"


@dataclass(frozen=True)
class Combination:
    election_id: str
    party: str | None
    members: re.Pattern[str]  # full match on the members' display names
    expected: int  # how many member contests the file must have
    name: str
    evidence: str


COMBINATIONS: tuple[Combination, ...] = (
    Combination(
        "franklin-2020-04-28-primary",
        "Dem",
        re.compile(
            r"Delegates-at-Large and Alternates-at-Large to the National Convention"
            r" \d+(?:st|nd|rd|th) Congressional District"
        ),
        3,
        "Delegates-at-Large and Alternates-at-Large to the National Convention (all districts)",
        "2020 primary: one contest per congressional district (3rd, 12th, 15th); requested"
        " 2026-10-22 as a countywide view.",
    ),
    Combination(
        "franklin-2020-04-28-primary",
        "Rep",
        re.compile(
            r"District Delegates and District Alternates to the National Convention"
            r" \d+(?:st|nd|rd|th) Congressional District"
        ),
        3,
        "District Delegates and District Alternates to the National Convention (all districts)",
        "2020 primary: one Republican contest per congressional district (3rd, 12th, 15th);"
        " requested 2026-10-22 alongside the Democratic one.",
    ),
)


def _choices(
    members: list[ContestSpec], ordinal: int
) -> tuple[list[ChoiceSpec], dict[tuple[int, int], int]]:
    """Union of member choices by (name, kind), and member (contest, choice) -> combined choice.

    The member with the most choices sets the order, so a choice missing from one district
    keeps its ballot position."""
    combined: list[ChoiceSpec] = []
    index: dict[tuple[str, str], int] = {}
    mapping: dict[tuple[int, int], int] = {}
    for c in sorted(members, key=lambda m: -len(m.choices)):
        for ch in c.choices:
            key = (ch.name_display, ch.kind)
            if key not in index:
                index[key] = len(combined)
                combined.append(
                    dataclasses.replace(
                        ch,
                        column=len(combined),
                        ordinal=len(combined),
                        sheet=combined_sheet(ordinal),
                    )
                )
            mapping[(c.ordinal, ch.ordinal)] = index[key]
    return combined, mapping


def _checks(
    parsed: ParsedFile,
    members: list[ContestSpec],
    mapping: dict[tuple[int, int], int],
    name: str,
    choices: list[ChoiceSpec],
) -> list[ColumnCheck]:
    by_col = {(c.sheet, c.column): c for c in parsed.column_checks}
    sums: dict[int, list[int]] = defaultdict(lambda: [0, 0, 0])
    for c in members:
        for ch in c.choices:
            src = by_col[(ch.sheet, ch.column)]
            acc = sums[mapping[(c.ordinal, ch.ordinal)]]
            acc[0] += src.precinct_sum
            acc[1] += src.out_of_county_sum
            acc[2] += src.county_total
    return [
        ColumnCheck(
            ch.column,
            f"{name} | {ch.name_display}",
            sums[ch.ordinal][0],
            sums[ch.ordinal][1],
            sums[ch.ordinal][2],
            ch.sheet,
        )
        for ch in choices
    ]


def _sum_rows(
    parsed: ParsedFile, mapping: dict[tuple[int, int], int], ordinal: int, choices: list[ChoiceSpec]
) -> tuple[list[ResultRow], list[OutOfCountyRow]]:
    """Combined rows: each precinct's (and other county's) votes summed over the members."""
    votes: dict[tuple[str, int], int] = defaultdict(int)
    for r in parsed.results:
        if (r.contest_ordinal, r.choice_ordinal) in mapping:
            votes[(r.precinct_name, mapping[(r.contest_ordinal, r.choice_ordinal)])] += r.votes
    present = sorted({p for p, _ in votes})
    results = [
        ResultRow(p, ordinal, ch.ordinal, votes.get((p, ch.ordinal), 0))
        for p in present
        for ch in choices
    ]
    outside: dict[tuple[str, int], int] = defaultdict(int)
    for o in parsed.out_of_county:
        if (o.contest_ordinal, o.choice_ordinal) in mapping:
            outside[(o.county_name, mapping[(o.contest_ordinal, o.choice_ordinal)])] += o.votes
    return results, [OutOfCountyRow(k, ordinal, ch, v) for (k, ch), v in outside.items()]


def _apply(parsed: ParsedFile, combo: Combination) -> ParsedFile:
    members = [
        c
        for c in parsed.contests
        if c.party == combo.party and combo.members.fullmatch(c.name_display)
    ]
    if len(members) != combo.expected:
        raise IngestError(
            f"combination {combo.name!r}: expected {combo.expected} member contests, found"
            f" {[c.name_display for c in members]}"
        )
    ordinal = len(parsed.contests)
    choices, mapping = _choices(members, ordinal)
    contest = ContestSpec(
        ordinal,
        " + ".join(c.name_raw for c in members),
        combo.name,
        combo.party,
        "candidate",
        None,
        tuple(choices),
    )
    results, outside = _sum_rows(parsed, mapping, ordinal, choices)
    log = parsed.normalizations
    log.add(
        "combined_contest",
        f"contest {ordinal}",
        " + ".join(c.name_display for c in members),
        combo.name,
    )
    return dataclasses.replace(
        parsed,
        contests=[*parsed.contests, contest],
        results=[*parsed.results, *results],
        out_of_county=[
            *parsed.out_of_county,
            *outside,
        ],
        column_checks=[
            *parsed.column_checks,
            *_checks(parsed, members, mapping, combo.name, choices),
        ],
    )


def combine(parsed: ParsedFile, election_id: str | None) -> ParsedFile:
    """Add every reviewed combined contest for `election_id` (no-op for other elections)."""
    for combo in COMBINATIONS:
        if combo.election_id == election_id:
            parsed = _apply(parsed, combo)
    return parsed
