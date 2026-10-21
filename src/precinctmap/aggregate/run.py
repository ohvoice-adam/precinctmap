"""Materialize and reconcile elections (all, or a chosen list)."""

import duckdb

from precinctmap.aggregate.materialize import materialize_election
from precinctmap.aggregate.reconcile import ReconcileSummary, reconcile_election


def election_ids(con: duckdb.DuckDBPyConnection) -> list[str]:
    return [r[0] for r in con.execute("SELECT election_id FROM elections ORDER BY 1").fetchall()]


def aggregate(
    con: duckdb.DuckDBPyConnection, elections: list[str] | None = None
) -> list[ReconcileSummary]:
    """Rebuild geo_* tables for each election and assert its totals reconcile."""
    out: list[ReconcileSummary] = []
    for e in elections or election_ids(con):
        out += reconcile_election(con, e, materialize_election(con, e))
    return out
