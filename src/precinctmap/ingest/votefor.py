"""Infer "vote for N" from over/under arithmetic. Display-only; shares never depend on it.

In a precinct where every ballot carries the contest,
    candidate votes + under votes + N * over votes == N * ballots cast.
Precincts with split ballot styles fail the identity for every N and are ignored. N is
'inferred' only when every precinct that satisfies the identity agrees on one N.
"""

from collections import defaultdict
from collections.abc import Mapping
from dataclasses import dataclass

from precinctmap.ingest.model import ContestSpec, ParsedFile

MAX_VOTE_FOR = 9


@dataclass(frozen=True)
class VoteFor:
    value: int | None
    source: str  # 'inferred' | 'unknown'
    evidence: str


def infer_vote_for(parsed: ParsedFile) -> dict[int, VoteFor]:
    """Contest ordinal -> VoteFor. Layouts without over/under columns are all 'unknown'."""
    if not parsed.has_over_under:
        reason = "layout has no OVER/UNDER VOTES columns"
        return {c.ordinal: VoteFor(None, "unknown", reason) for c in parsed.contests}
    ballots = {
        (t.precinct_name, t.party): t.ballots_cast
        for t in parsed.turnout
        if t.ballots_cast is not None
    }
    cells: dict[tuple[int, str], dict[int, int]] = defaultdict(dict)
    for r in parsed.results:
        cells[(r.contest_ordinal, r.precinct_name)][r.choice_ordinal] = r.votes
    by_contest: dict[int, list[tuple[str, dict[int, int]]]] = defaultdict(list)
    for (ordinal, precinct), votes in cells.items():
        by_contest[ordinal].append((precinct, votes))
    return {
        c.ordinal: _infer_one(c, by_contest.get(c.ordinal, []), ballots) for c in parsed.contests
    }


def _infer_one(
    contest: ContestSpec,
    cells: list[tuple[str, dict[int, int]]],
    ballots: Mapping[tuple[str, str], int],
) -> VoteFor:
    over = [ch.ordinal for ch in contest.choices if ch.kind == "over"]
    if len(over) != 1:
        return VoteFor(None, "unknown", "contest has no single OVER VOTES column")
    party = contest.party or "ALL"
    found: set[int] = set()
    fits = 0
    for precinct, votes in cells:
        b = ballots.get((precinct, party))
        if not b:
            continue
        ov = votes.get(over[0], 0)
        rest = sum(v for o, v in votes.items() if o != over[0])
        k = next((k for k in range(1, MAX_VOTE_FOR + 1) if rest + k * ov == k * b), None)
        if k is not None:
            found.add(k)
            fits += 1
    if len(found) == 1:
        n = found.pop()
        return VoteFor(n, "inferred", f"{fits}/{len(cells)} precincts fit N={n}")
    detail = f"candidates {sorted(found)}" if found else "no precinct fits"
    return VoteFor(None, "unknown", f"{detail} across {len(cells)} precincts")
