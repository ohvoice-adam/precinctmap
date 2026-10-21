"""Rule 4: per choice and geography, source = mapped + excluded + unassigned. Asserted."""

from dataclasses import dataclass

import duckdb

from precinctmap.aggregate.materialize import Target, targets_for

TOLERANCE = 1e-6  # relative; allocation sums floating-point shares

_RECONCILE = """
WITH covered AS (
    {covered}
), excluded AS (
    SELECT DISTINCT precinct_name FROM crosswalk_log
    WHERE precinct_set_id = $pset AND target_set_id = $tset AND issue = 'excluded'
), src AS (
    SELECT contest_id, choice_id, precinct_name, votes FROM precinct_results WHERE election_id = $e
), mapped AS (
    SELECT choice_id, sum(votes) AS v FROM geo_results
    WHERE election_id = $e AND geography = $geo GROUP BY 1
), totals AS (
    SELECT s.contest_id, s.choice_id, sum(s.votes) AS source,
           coalesce(sum(s.votes) FILTER (WHERE s.precinct_name IN (SELECT * FROM excluded)), 0)
               AS excluded,
           coalesce(sum(s.votes) FILTER (WHERE s.precinct_name NOT IN (SELECT * FROM covered)
               AND s.precinct_name NOT IN (SELECT * FROM excluded)), 0) AS unassigned
    FROM src s GROUP BY 1, 2
)
INSERT INTO geo_reconciliation
SELECT $e, t.contest_id, t.choice_id, $geo, t.source, coalesce(m.v, 0), t.excluded,
       t.unassigned,
       abs(t.source - coalesce(m.v, 0) - t.excluded - t.unassigned)
           <= $tol * greatest(t.source, 1)
FROM totals t LEFT JOIN mapped m USING (choice_id)
"""
_COVERED_IDENTITY = "SELECT feature_id AS precinct_name FROM features WHERE boundary_set_id = $pset"
_COVERED_CROSSWALK = (
    "SELECT DISTINCT precinct_name FROM precinct_crosswalk"
    " WHERE precinct_set_id = $pset AND target_set_id = $tset"
)


class ReconciliationError(AssertionError):
    pass


@dataclass(frozen=True)
class ReconcileSummary:
    election_id: str
    geography: str
    choices: int
    failures: int
    source: float
    mapped: float
    excluded: float
    unassigned: float


def reconcile_election(
    con: duckdb.DuckDBPyConnection, election_id: str, targets: list[Target] | None = None
) -> list[ReconcileSummary]:
    """Write geo_reconciliation for the election; raise if any choice fails to reconcile."""
    targets = targets or targets_for(con, election_id)
    con.execute("DELETE FROM geo_reconciliation WHERE election_id = ?", [election_id])
    for t in targets:
        covered = _COVERED_IDENTITY if t.geography == "precinct" else _COVERED_CROSSWALK
        sql = _RECONCILE.format(covered=covered)
        con.execute(
            sql,
            {
                "e": election_id,
                "geo": t.geography,
                "pset": t.precinct_set_id,
                "tset": t.target_set_id,
                "tol": TOLERANCE,
            },
        )
    rows = con.execute(
        "SELECT geography, count(*), count(*) FILTER (WHERE NOT ok), sum(source), sum(mapped),"
        " sum(excluded), sum(unassigned) FROM geo_reconciliation WHERE election_id = ?"
        " GROUP BY 1 ORDER BY 1",
        [election_id],
    ).fetchall()
    out = [ReconcileSummary(election_id, *r) for r in rows]
    bad = [s for s in out if s.failures]
    if bad:
        raise ReconciliationError(
            f"{election_id}: totals do not reconcile for "
            + ", ".join(f"{s.geography} ({s.failures} choices)" for s in bad)
            + "; see geo_reconciliation"
        )
    return out
