"""The selection tree the map client walks: year -> election -> contest -> choice -> geography.

Only options with data are listed: geographies appear for an election only if geo_results
exist for it.
"""

from collections import defaultdict
from typing import Any

import duckdb

from precinctmap.serve.census import census_catalog
from precinctmap.serve.labels import GEOGRAPHY_LABELS
from precinctmap.serve.property import property_catalog
from precinctmap.serve.turnout import turnout_contest

_ELECTIONS = """
SELECT e.election_id, e.election_date, e.election_type, e.label, e.certified, f.filename,
       (SELECT list(DISTINCT party ORDER BY party) FROM precinct_turnout t
         WHERE t.election_id = e.election_id) AS turnout_parties
FROM elections e
LEFT JOIN source_files f ON f.election_id = e.election_id AND f.status = 'active'
ORDER BY e.election_date DESC
"""

_GEOGRAPHIES = """
SELECT DISTINCT r.election_id, r.geography, r.boundary_set_id,
       e.election_date < coalesce(b.native_from, DATE '0001-01-01') AS retroactive
FROM geo_results r
JOIN elections e USING (election_id)
JOIN boundary_sets b ON b.boundary_set_id = r.boundary_set_id
"""

_CONTESTS = """
SELECT c.election_id, c.contest_id, c.name_display, c.party, c.contest_type, c.vote_for,
       c.jurisdiction, c.source_ordinal,
       (SELECT count(DISTINCT precinct_name) FROM precinct_results r
         WHERE r.contest_id = c.contest_id) AS precincts,
       (SELECT list(DISTINCT county_name ORDER BY county_name) FROM out_of_county_results o
         WHERE o.contest_id = c.contest_id) AS other_counties
FROM contests c ORDER BY c.election_id, c.source_ordinal
"""

_CHOICES = """
SELECT contest_id, choice_id, name_display, party, choice_kind
FROM choices ORDER BY contest_id, source_ordinal
"""

GEOGRAPHY_ORDER = ("precinct", "council_district", "municipality", "ward", "zcta")


def _choices(con: duckdb.DuckDBPyConnection) -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for contest_id, choice_id, name, party, kind in con.execute(_CHOICES).fetchall():
        out[contest_id].append({"choice_id": choice_id, "name": name, "party": party, "kind": kind})
    return out


def _contests(con: duckdb.DuckDBPyConnection) -> dict[str, list[dict[str, Any]]]:
    choices = _choices(con)
    out: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in con.execute(_CONTESTS).fetchall():
        e_id, c_id, name, party, ctype, vote_for, juris, _, precincts, others = row
        out[e_id].append(
            {
                "contest_id": c_id,
                "name": name,
                "party": party,
                "type": ctype,
                "vote_for": vote_for,
                "jurisdiction": juris,
                "precincts": precincts,
                "other_counties": others or [],
                "choices": choices[c_id],
            }
        )
    return out


def _geographies(con: duckdb.DuckDBPyConnection) -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for e_id, geo, set_id, retro in con.execute(_GEOGRAPHIES).fetchall():
        out[e_id].append(
            {
                "geography": geo,
                "label": GEOGRAPHY_LABELS[geo],
                "boundary_set_id": set_id,
                "retroactive": bool(retro),
            }
        )
    for geos in out.values():
        geos.sort(key=lambda g: GEOGRAPHY_ORDER.index(g["geography"]))
    return out


def catalog(con: duckdb.DuckDBPyConnection) -> dict[str, Any]:
    contests, geographies = _contests(con), _geographies(con)
    elections = []
    for e_id, on, etype, label, certified, filename, parties in con.execute(_ELECTIONS).fetchall():
        if not geographies.get(e_id):
            continue  # not aggregated yet: nothing to map
        elections.append(
            {
                "election_id": e_id,
                "date": on.isoformat(),
                "year": on.year,
                "type": etype,
                "label": label,
                "certified": certified,
                "source_file": filename,
                "turnout_parties": parties or [],
                "geographies": geographies[e_id],
                # Turnout leads the contest list when the file had registered and ballot counts.
                "contests": [t for t in [turnout_contest(con, e_id)] if t] + contests.get(e_id, []),
            }
        )
    return {
        "years": sorted({e["year"] for e in elections}, reverse=True),
        "elections": elections,
        "property": property_catalog(con),
        "census": census_catalog(con),
    }
