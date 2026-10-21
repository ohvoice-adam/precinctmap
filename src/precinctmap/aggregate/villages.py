"""Check village allocations against ballots actually cast in each village's own contests.

A village with no precincts of its own is allocated from its host precinct by 2020 block
population. Its own contests (e.g. 'Village of Brice' council) appear only on village voters'
ballots, so ballots-in-contest / precinct ballots is a direct measure of the village's share
of that precinct's voters. Ballots in a contest = (candidate + under votes) / N + over votes,
with N = vote-for (1 for issues); candidate contests with unknown N are skipped.
"""

from dataclasses import dataclass

import duckdb

from precinctmap.aggregate.materialize import targets_for

_SQL = """
WITH alloc AS (
    SELECT x.precinct_name, x.feature_id, f.name, x.split_share
    FROM precinct_crosswalk x
    JOIN features f ON f.boundary_set_id = x.target_set_id AND f.feature_id = x.feature_id
    WHERE x.precinct_set_id = $pset AND x.target_set_id = $tset AND x.method = 'allocated'
      AND f.jurisdiction IN ('village', 'city')
), contest_ballots AS (
    SELECT c.contest_id, c.name_display, c.jurisdiction, r.precinct_name,
           sum(r.votes) FILTER (WHERE h.choice_kind <> 'over')
               / (CASE WHEN c.contest_type = 'issue' THEN 1 ELSE c.vote_for END)
             + coalesce(sum(r.votes) FILTER (WHERE h.choice_kind = 'over'), 0) AS ballots
    FROM contests c
    JOIN precinct_results r ON r.contest_id = c.contest_id
    JOIN choices h ON h.choice_id = r.choice_id
    WHERE c.election_id = $e AND (c.contest_type = 'issue' OR c.vote_for IS NOT NULL)
    GROUP BY c.contest_id, c.name_display, c.jurisdiction, c.contest_type, c.vote_for,
             r.precinct_name
)
SELECT a.name, a.precinct_name, a.split_share, t.ballots_cast,
       max(cb.ballots) AS village_ballots, count(DISTINCT cb.contest_id) AS contests
FROM alloc a
JOIN precinct_turnout t ON t.election_id = $e AND t.precinct_name = a.precinct_name
     AND t.party = 'ALL'
LEFT JOIN contest_ballots cb ON cb.precinct_name = a.precinct_name
     AND (cb.jurisdiction = 'Village of ' || a.name OR cb.jurisdiction = 'City of ' || a.name)
GROUP BY ALL ORDER BY a.name
"""


@dataclass(frozen=True)
class VillageCheck:
    election_id: str
    village: str
    host_precinct: str
    population_share: float
    precinct_ballots: int | None
    village_ballots: float | None  # None: no village contest with known vote-for this election
    contests: int

    @property
    def ballot_share(self) -> float | None:
        if self.village_ballots is None or not self.precinct_ballots:
            return None
        return self.village_ballots / self.precinct_ballots


def village_checks(con: duckdb.DuckDBPyConnection, election_id: str) -> list[VillageCheck]:
    muni = next((t for t in targets_for(con, election_id) if t.geography == "municipality"), None)
    if muni is None:
        return []
    rows = con.execute(
        _SQL, {"e": election_id, "pset": muni.precinct_set_id, "tset": muni.target_set_id}
    ).fetchall()
    return [
        VillageCheck(election_id, name, p, share, bal, vb, n) for name, p, share, bal, vb, n in rows
    ]
