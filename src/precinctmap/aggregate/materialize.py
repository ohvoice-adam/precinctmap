"""Materialize geo_results / geo_turnout / geo_contributions for one election.

Votes flow through the crosswalk of (the precinct set valid on the election date, the target
set valid on that date): votes x split_share, summed per feature. The precinct geography uses
an identity crosswalk. Everything for the election is replaced in one transaction.
"""

import logging
from dataclasses import dataclass

import duckdb

from precinctmap.registry.store import BoundaryError, set_for

log = logging.getLogger(__name__)

GEOGRAPHIES = ("precinct", "council_district", "municipality", "zcta")

# A CTE named xw: precinct_name, feature_id, split_share, method, weight_basis.
_XW_IDENTITY = """xw AS (
    SELECT feature_id AS precinct_name, feature_id, 1.0 AS split_share,
           'exact' AS method, 'identity' AS weight_basis
    FROM features WHERE boundary_set_id = $pset)"""
_XW_CROSSWALK = """xw AS (
    SELECT precinct_name, feature_id, split_share, method, weight_basis
    FROM precinct_crosswalk WHERE precinct_set_id = $pset AND target_set_id = $tset)"""

_RESULTS = """
WITH {xw}, parts AS (
    SELECT r.contest_id, r.choice_id, x.feature_id, r.precinct_name, x.method,
           r.votes * x.split_share AS v
    FROM precinct_results r JOIN xw x USING (precinct_name)
    WHERE r.election_id = $e
)
INSERT INTO geo_results
SELECT $e, contest_id, choice_id, $geo, $tset, feature_id,
       sum(v), coalesce(sum(v) FILTER (WHERE method = 'exact'), 0),
       coalesce(sum(v) FILTER (WHERE method = 'allocated'), 0),
       count(DISTINCT precinct_name) FILTER (WHERE method = 'exact'),
       count(DISTINCT precinct_name) FILTER (WHERE method = 'allocated'),
       CASE WHEN bool_and(method = 'exact') THEN 'exact'
            WHEN bool_and(method = 'allocated') THEN 'allocated' ELSE 'mixed' END
FROM parts GROUP BY contest_id, choice_id, feature_id
"""

_TURNOUT = """
WITH {xw}
INSERT INTO geo_turnout
SELECT $e, $geo, $tset, x.feature_id, t.party,
       sum(t.registered * x.split_share), sum(t.ballots_cast * x.split_share),
       sum(t.ballots_blank * x.split_share)
FROM precinct_turnout t JOIN xw x USING (precinct_name)
WHERE t.election_id = $e GROUP BY x.feature_id, t.party
"""

_CONTRIBUTIONS = """
WITH {xw}
INSERT INTO geo_contributions
SELECT $e, $geo, $tset, x.feature_id, x.precinct_name, x.split_share, x.method, x.weight_basis
FROM xw x JOIN precinct_sources s ON s.precinct_name = x.precinct_name AND s.election_id = $e
"""


@dataclass(frozen=True)
class Target:
    geography: str
    target_set_id: str
    precinct_set_id: str
    retroactive: bool


def targets_for(con: duckdb.DuckDBPyConnection, election_id: str) -> list[Target]:
    row = con.execute(
        "SELECT election_date, county FROM elections WHERE election_id = ?", [election_id]
    ).fetchone()
    if row is None:
        raise BoundaryError(f"unknown election {election_id}")
    on, county = row
    pset = set_for(con, "precinct", county, on)
    if pset is None:
        raise BoundaryError(f"{election_id}: no precinct boundary set covers {on}")
    out = [Target("precinct", pset.boundary_set_id, pset.boundary_set_id, pset.retroactive)]
    for geo in GEOGRAPHIES[1:]:
        ref = set_for(con, geo, county, on)  # type: ignore[arg-type]
        if ref is None:
            log.warning("%s: no %s boundary set covers %s; skipped", election_id, geo, on)
            continue
        out.append(Target(geo, ref.boundary_set_id, pset.boundary_set_id, ref.retroactive))
    return out


def materialize_election(con: duckdb.DuckDBPyConnection, election_id: str) -> list[Target]:
    """Replace this election's materialized rows for every geography with a boundary set."""
    targets = targets_for(con, election_id)
    con.execute("BEGIN")
    try:
        for table in ("geo_results", "geo_turnout", "geo_contributions"):
            con.execute(f"DELETE FROM {table} WHERE election_id = ?", [election_id])
        for t in targets:
            xw = _XW_IDENTITY if t.geography == "precinct" else _XW_CROSSWALK
            params = {
                "e": election_id,
                "geo": t.geography,
                "pset": t.precinct_set_id,
                "tset": t.target_set_id,
            }
            for sql in (_RESULTS, _TURNOUT, _CONTRIBUTIONS):
                text = sql.format(xw=xw)
                con.execute(text, {k: v for k, v in params.items() if f"${k}" in text})
        con.execute("COMMIT")
    except Exception:
        con.execute("ROLLBACK")
        raise
    return targets
