"""Read-side catalog queries (used by the CLI now and the API in Phase 5)."""

from typing import Any

import duckdb

_ELECTIONS = """
WITH pc AS (
    SELECT election_id, count(*) AS precincts FROM precinct_sources GROUP BY 1
), ct AS (
    SELECT election_id, count(*) AS contests,
           count(*) FILTER (WHERE vote_for_source = 'inferred') AS vote_for_known
    FROM contests GROUP BY 1
), tu AS (
    SELECT election_id, sum(registered) AS registered, sum(ballots_cast) AS ballots
    FROM precinct_turnout WHERE party = 'ALL' GROUP BY 1
), bs AS (
    SELECT e.election_id, b.boundary_set_id,
           e.election_date < coalesce(b.native_from, DATE '0001-01-01') AS retroactive
    FROM elections e JOIN boundary_sets b
      ON b.geography = 'precinct' AND b.county = e.county AND b.valid_from <= e.election_date
     AND (b.valid_to IS NULL OR e.election_date < b.valid_to)
), mt AS (
    SELECT s.election_id, count(f.feature_id) AS matched
    FROM precinct_sources s JOIN bs USING (election_id)
    LEFT JOIN features f
      ON f.boundary_set_id = bs.boundary_set_id AND f.feature_id = s.precinct_name
    GROUP BY 1
)
SELECT e.election_id, e.election_date, e.election_type, e.certified, e.label,
       f.filename, f.adapter || ' v' || f.adapter_version AS adapter,
       pc.precincts, ct.contests, ct.vote_for_known, tu.registered, tu.ballots,
       bs.boundary_set_id, bs.retroactive, mt.matched,
       (SELECT count(*) FROM source_files s
         WHERE s.election_id = e.election_id AND s.status = 'superseded') AS superseded_files
FROM elections e
LEFT JOIN source_files f ON f.election_id = e.election_id AND f.status = 'active'
LEFT JOIN pc ON pc.election_id = e.election_id
LEFT JOIN ct ON ct.election_id = e.election_id
LEFT JOIN tu ON tu.election_id = e.election_id
LEFT JOIN bs ON bs.election_id = e.election_id
LEFT JOIN mt ON mt.election_id = e.election_id
ORDER BY e.election_date, e.election_type
"""

_CONTESTS = """
SELECT c.source_ordinal, c.contest_id, c.party, c.name_display, c.contest_type,
       c.vote_for, c.vote_for_source,
       (SELECT count(*) FROM choices h WHERE h.contest_id = c.contest_id
          AND h.choice_kind NOT IN ('over', 'under')) AS choices,
       (SELECT count(DISTINCT precinct_name) FROM precinct_results r
         WHERE r.contest_id = c.contest_id) AS precincts,
       (SELECT coalesce(sum(votes), 0) FROM precinct_results r JOIN choices h USING (choice_id)
         WHERE r.contest_id = c.contest_id AND h.choice_kind NOT IN ('over', 'under')) AS votes
FROM contests c WHERE c.election_id = ? ORDER BY c.source_ordinal
"""


def _rows(cur: duckdb.DuckDBPyConnection) -> list[dict[str, Any]]:
    cols = [d[0] for d in cur.description or []]
    return [dict(zip(cols, row, strict=True)) for row in cur.fetchall()]


def elections_summary(con: duckdb.DuckDBPyConnection) -> list[dict[str, Any]]:
    """One row per election: active file, counts, turnout, and live precinct match."""
    return _rows(con.execute(_ELECTIONS))


def contests_summary(con: duckdb.DuckDBPyConnection, election_id: str) -> list[dict[str, Any]]:
    """Contests of one election with choice count, precinct coverage, and valid votes."""
    return _rows(con.execute(_CONTESTS, [election_id]))
