"""Per-election boundary coverage: precinct match rate and crosswalk stats per geography."""

from dataclasses import dataclass, field
from typing import Any

import duckdb

from precinctmap.registry.crosswalk_build import TARGET_GEOGRAPHIES
from precinctmap.registry.store import set_for


@dataclass
class GeographyCoverage:
    geography: str
    target_set_id: str | None
    retroactive: bool = False
    exact: int = 0
    allocated: int = 0
    excluded: int = 0
    no_overlap: int = 0
    missing: list[str] = field(default_factory=list)  # matched precincts absent from crosswalk


@dataclass
class ElectionCoverage:
    election_id: str
    precinct_set_id: str | None
    retroactive: bool
    precincts: int
    matched: int
    unmatched: list[str]
    geographies: list[GeographyCoverage]


def _names(con: duckdb.DuckDBPyConnection, sql: str, params: list[Any]) -> set[str]:
    return {r[0] for r in con.execute(sql, params).fetchall()}


def _geo(
    con: duckdb.DuckDBPyConnection, e: tuple[Any, ...], pset: str, names: set[str], geo: str
) -> GeographyCoverage:
    election_date, county = e[1], e[2]
    ref = set_for(con, geo, county, election_date)  # type: ignore[arg-type]
    cov = GeographyCoverage(geo, ref.boundary_set_id if ref else None)
    if ref is None:
        return cov
    cov.retroactive = ref.retroactive
    rows = con.execute(
        "SELECT precinct_name, any_value(method) FROM precinct_crosswalk"
        " WHERE precinct_set_id = ? AND target_set_id = ? GROUP BY 1",
        [pset, ref.boundary_set_id],
    ).fetchall()
    methods = {n: m for n, m in rows if n in names}
    logged = con.execute(
        "SELECT precinct_name, issue FROM crosswalk_log WHERE precinct_set_id = ?"
        " AND target_set_id = ? AND issue IN ('excluded', 'no_overlap')",
        [pset, ref.boundary_set_id],
    ).fetchall()
    issues = {n: i for n, i in logged if n in names}
    cov.exact = sum(m == "exact" for m in methods.values())
    cov.allocated = sum(m == "allocated" for m in methods.values())
    cov.excluded = sum(i == "excluded" for i in issues.values())
    cov.no_overlap = sum(i == "no_overlap" for i in issues.values())
    cov.missing = sorted(names - set(methods) - set(issues))
    return cov


def coverage(con: duckdb.DuckDBPyConnection) -> list[ElectionCoverage]:
    out = []
    elections = con.execute(
        "SELECT election_id, election_date, county FROM elections ORDER BY election_date"
    ).fetchall()
    for e in elections:
        results = _names(
            con, "SELECT precinct_name FROM precinct_sources WHERE election_id = ?", [e[0]]
        )
        ref = set_for(con, "precinct", e[2], e[1])
        if ref is None:
            out.append(ElectionCoverage(e[0], None, False, len(results), 0, sorted(results), []))
            continue
        features = _names(
            con, "SELECT feature_id FROM features WHERE boundary_set_id = ?", [ref.boundary_set_id]
        )
        matched = results & features
        geos = [_geo(con, e, ref.boundary_set_id, matched, g) for g in TARGET_GEOGRAPHIES]
        out.append(
            ElectionCoverage(
                e[0],
                ref.boundary_set_id,
                ref.retroactive,
                len(results),
                len(matched),
                sorted(results - features),
                geos,
            )
        )
    return out
