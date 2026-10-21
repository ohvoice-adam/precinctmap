"""Results payloads: compact per-feature votes for the map, and the per-area detail.

Votes are listed in the contest's choice order. Allocated votes are fractional and rounded
to 2 decimals here; shares use valid votes (every choice except over/under votes).
"""

from typing import Any

import duckdb

from precinctmap.ingest.model import NON_VOTE_KINDS
from precinctmap.serve.labels import (
    FRANKLIN_ONLY,
    GEOGRAPHY_LABELS,
    NOT_IN_COLUMBUS,
    RETROACTIVE_PRECINCTS,
    ZCTA_NOTE,
)


class NotFoundError(LookupError):
    pass


def contest_info(
    con: duckdb.DuckDBPyConnection, election_id: str, contest_id: str
) -> dict[str, Any]:
    row = con.execute(
        "SELECT c.name_display, c.party, c.contest_type, c.vote_for, f.filename, f.file_id"
        " FROM contests c JOIN source_files f ON f.file_id = c.file_id"
        " WHERE c.election_id = ? AND c.contest_id = ?",
        [election_id, contest_id],
    ).fetchone()
    if row is None:
        raise NotFoundError(f"no contest {contest_id!r} in {election_id!r}")
    choices = [
        {"choice_id": i, "name": n, "party": p, "kind": k, "counts": k not in NON_VOTE_KINDS}
        for i, n, p, k in con.execute(
            "SELECT choice_id, name_display, party, choice_kind FROM choices"
            " WHERE contest_id = ? ORDER BY source_ordinal",
            [contest_id],
        ).fetchall()
    ]
    name, party, ctype, vote_for, filename, file_id = row
    return {
        "name": name,
        "party": party,
        "type": ctype,
        "vote_for": vote_for,
        "source_file": filename,
        "file_id": file_id,
        "choices": choices,
    }


def geo_set(con: duckdb.DuckDBPyConnection, election_id: str, geography: str) -> tuple[str, bool]:
    row = con.execute(
        "SELECT DISTINCT r.boundary_set_id,"
        " e.election_date < coalesce(b.native_from, DATE '0001-01-01')"
        " FROM geo_results r JOIN elections e USING (election_id)"
        " JOIN boundary_sets b ON b.boundary_set_id = r.boundary_set_id"
        " WHERE r.election_id = ? AND r.geography = ?",
        [election_id, geography],
    ).fetchall()
    if len(row) != 1:
        raise NotFoundError(f"no {geography} results for {election_id!r}")
    return str(row[0][0]), bool(row[0][1])


def _notes(
    con: duckdb.DuckDBPyConnection, contest_id: str, geography: str, retro: bool, excluded: float
) -> list[str]:
    notes = []
    if retro and geography in ("precinct", "municipality"):
        notes.append(RETROACTIVE_PRECINCTS)
    others = con.execute(
        "SELECT county_name, sum(votes) FROM out_of_county_results WHERE contest_id = ?"
        " GROUP BY 1 ORDER BY 1",
        [contest_id],
    ).fetchall()
    if others:
        listed = ", ".join(f"{c} ({int(v):,})" for c, v in others)
        notes.append(f"{FRANKLIN_ONLY} Votes from other counties are not mapped: {listed}.")
    if geography == "council_district" and excluded > 0:
        notes.append(f"{NOT_IN_COLUMBUS} {excluded:,.0f} votes in this contest are not shown.")
    if geography == "zcta":
        notes.append(ZCTA_NOTE)
    return notes


def results(
    con: duckdb.DuckDBPyConnection, election_id: str, contest_id: str, geography: str
) -> dict[str, Any]:
    contest = contest_info(con, election_id, contest_id)
    set_id, retro = geo_set(con, election_id, geography)
    order = {c["choice_id"]: i for i, c in enumerate(contest["choices"])}
    features: dict[str, dict[str, Any]] = {}
    for fid, reg, bal in con.execute(
        "SELECT feature_id, registered, ballots_cast FROM geo_turnout"
        " WHERE election_id = ? AND geography = ? AND party = 'ALL'",
        [election_id, geography],
    ).fetchall():
        features[fid] = {"v": None, "reg": _r(reg), "bal": _r(bal)}
    for fid, choice, votes, method, pe, pa in con.execute(
        "SELECT feature_id, choice_id, votes, method, precincts_exact, precincts_allocated"
        " FROM geo_results WHERE election_id = ? AND geography = ? AND contest_id = ?",
        [election_id, geography, contest_id],
    ).fetchall():
        f = features.setdefault(fid, {"v": None, "reg": None, "bal": None})
        if f["v"] is None:
            f.update(v=[0.0] * len(order), method=method, pe=pe, pa=pa)
        f["v"][order[choice]] = _r(votes)
    rec = con.execute(
        "SELECT coalesce(sum(source), 0), coalesce(sum(mapped), 0), coalesce(sum(excluded), 0)"
        " FROM geo_reconciliation r JOIN choices h USING (choice_id)"
        " WHERE r.election_id = ? AND r.geography = ? AND r.contest_id = ?"
        " AND h.choice_kind NOT IN ('over', 'under')",
        [election_id, geography, contest_id],
    ).fetchone() or (0, 0, 0)
    return {
        "election_id": election_id,
        "contest_id": contest_id,
        "contest": contest["name"],
        "party": contest["party"],
        "type": contest["type"],
        "vote_for": contest["vote_for"],
        "geography": geography,
        "geography_label": GEOGRAPHY_LABELS[geography],
        "boundary_set_id": set_id,
        "retroactive": retro,
        "source_file": contest["source_file"],
        "choices": contest["choices"],
        "totals": {"valid_votes": _r(rec[0]), "mapped": _r(rec[1]), "excluded": _r(rec[2])},
        "notes": _notes(con, contest_id, geography, retro, float(rec[2])),
        "features": features,
    }


def _r(x: float | None) -> float | None:
    return None if x is None else round(float(x), 2)
