"""Turnout for an election, by geography: registered voters, ballots cast, and party ballots.

Listed in the catalog as the first "contest" of each election that has turnout, with id
`<election_id>:turnout` and one choice per party ballot. Values come from `geo_turnout`
(aggregated and allocated like votes). Party percentages are offered two ways: party ballots
over all registered voters (they add up to turnout), and over all ballots cast (each party's
share of the electorate). The files' "registered by party" counts are not used as a
denominator: they count voters by their last primary ballot, so they can be below that party's
ballots.
"""

from typing import Any

import duckdb

from precinctmap.serve.labels import (
    GEOGRAPHY_LABELS,
    NOT_IN_COLUMBUS,
    RETROACTIVE_COUNCIL,
    RETROACTIVE_PRECINCTS,
    ZCTA_NOTE,
)
from precinctmap.serve.results import NotFoundError, geo_set

SUFFIX = ":turnout"
PARTY_LABELS = {
    "Dem": "Democratic ballots",
    "Rep": "Republican ballots",
    "Lib": "Libertarian ballots",
    "Grn": "Green ballots",
    "Non": "Nonpartisan ballots (issues only)",
}
TURNOUT_NOTE = (
    "Turnout is ballots cast divided by registered voters. Party ballots are the primary ballot"
    " voters chose; '% of registered' divides by all registered voters, '% of ballots' by all"
    " ballots cast."
)


def turnout_id(election_id: str) -> str:
    return f"{election_id}{SUFFIX}"


def is_turnout(contest_id: str) -> bool:
    return contest_id.endswith(SUFFIX)


def _parties(con: duckdb.DuckDBPyConnection, election_id: str) -> list[str]:
    rows = con.execute(
        "SELECT DISTINCT party FROM precinct_turnout WHERE election_id = ? AND party <> 'ALL'"
        " AND ballots_cast IS NOT NULL",
        [election_id],
    ).fetchall()
    order = list(PARTY_LABELS)
    return sorted((p for (p,) in rows), key=lambda p: (order.index(p) if p in order else 99, p))


def _choices(election_id: str, parties: list[str]) -> list[dict[str, Any]]:
    return [
        {
            "choice_id": f"{turnout_id(election_id)}:{p}",
            "name": PARTY_LABELS.get(p, f"{p} ballots"),
            "party": p,
            "kind": "party",
            "counts": True,
        }
        for p in parties
    ]


def turnout_contest(con: duckdb.DuckDBPyConnection, election_id: str) -> dict[str, Any] | None:
    """The catalog entry, or None when the election's file had no registered/ballot counts."""
    row = con.execute(
        "SELECT count(*) FROM precinct_turnout WHERE election_id = ? AND party = 'ALL'"
        " AND registered IS NOT NULL AND ballots_cast IS NOT NULL",
        [election_id],
    ).fetchone()
    if not row or not row[0]:
        return None
    choices = _choices(election_id, _parties(con, election_id))
    return {
        "contest_id": turnout_id(election_id),
        "name": "Turnout",
        "party": None,
        "type": "turnout",
        "vote_for": None,
        "jurisdiction": None,
        "precincts": int(row[0]),
        "other_counties": [],
        "choices": [{k: v for k, v in c.items() if k != "counts"} for c in choices],
    }


def _source(con: duckdb.DuckDBPyConnection, election_id: str) -> tuple[str, str]:
    row = con.execute(
        "SELECT filename, file_id FROM source_files WHERE election_id = ? AND status = 'active'",
        [election_id],
    ).fetchone()
    if row is None:
        raise NotFoundError(f"no loaded file for {election_id!r}")
    return str(row[0]), str(row[1])


def _r(x: float | None) -> float | None:
    return None if x is None else round(float(x), 2)


def _methods(con: duckdb.DuckDBPyConnection, e: str, geo: str) -> dict[str, tuple[str, int, int]]:
    """feature -> (exact | allocated | mixed, precincts exact, precincts allocated)."""
    out = {}
    for fid, pe, pa in con.execute(
        "SELECT feature_id, count(*) FILTER (WHERE method = 'exact'),"
        " count(*) FILTER (WHERE method <> 'exact') FROM geo_contributions"
        " WHERE election_id = ? AND geography = ? GROUP BY 1",
        [e, geo],
    ).fetchall():
        out[fid] = ("exact" if not pa else "allocated" if not pe else "mixed", int(pe), int(pa))
    return out


def _notes(geography: str, retro: bool, excluded: float) -> list[str]:
    notes = [TURNOUT_NOTE]
    if retro and geography in ("precinct", "municipality", "ward"):
        notes.append(RETROACTIVE_PRECINCTS)
    if retro and geography == "council_district":
        notes.append(RETROACTIVE_COUNCIL)
    if geography == "council_district" and excluded > 0:
        notes.append(f"{NOT_IN_COLUMBUS} {excluded:,.0f} ballots are not shown.")
    if geography == "zcta":
        notes.append(ZCTA_NOTE)
    return notes


def _features(
    con: duckdb.DuckDBPyConnection, e: str, geo: str, parties: list[str]
) -> dict[str, dict[str, Any]]:
    methods = _methods(con, e, geo)
    features: dict[str, dict[str, Any]] = {}
    for fid, party, reg, bal in con.execute(
        "SELECT feature_id, party, registered, ballots_cast FROM geo_turnout"
        " WHERE election_id = ? AND geography = ?",
        [e, geo],
    ).fetchall():
        method, pe, pa = methods.get(fid, (None, None, None))
        f = features.setdefault(
            fid,
            {
                "v": [0.0] * len(parties),
                "reg": None,
                "bal": None,
                "method": method,
                "pe": pe,
                "pa": pa,
            },
        )
        if party == "ALL":
            f["reg"], f["bal"] = _r(reg), _r(bal)
        elif party in parties:
            f["v"][parties.index(party)] = _r(bal) or 0.0
    return features


def turnout_results(
    con: duckdb.DuckDBPyConnection, election_id: str, geography: str
) -> dict[str, Any]:
    """Same shape as a contest's results: `v` holds ballots per party, in `choices` order."""
    parties = _parties(con, election_id)
    set_id, retro = geo_set(con, election_id, geography)
    features = _features(con, election_id, geography, parties)
    total = con.execute(
        "SELECT sum(ballots_cast) FROM precinct_turnout WHERE election_id = ? AND party = 'ALL'",
        [election_id],
    ).fetchone()
    source = float((total or (0,))[0] or 0)
    mapped = sum(f["bal"] or 0 for f in features.values())
    filename, _ = _source(con, election_id)
    return {
        "election_id": election_id,
        "contest_id": turnout_id(election_id),
        "contest": "Turnout",
        "party": None,
        "type": "turnout",
        "vote_for": None,
        "geography": geography,
        "geography_label": GEOGRAPHY_LABELS[geography],
        "boundary_set_id": set_id,
        "retroactive": retro,
        "source_file": filename,
        "choices": _choices(election_id, parties),
        "totals": {
            "valid_votes": _r(source),
            "mapped": _r(mapped),
            "excluded": _r(max(source - mapped, 0)),
        },
        "notes": _notes(geography, retro, max(source - mapped, 0)),
        "features": features,
    }
