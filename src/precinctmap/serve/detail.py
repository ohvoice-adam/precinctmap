"""The click detail for one area: every choice's votes and share, method, precincts, source."""

from typing import Any

import duckdb

from precinctmap.serve.results import NotFoundError, contest_info, geo_set


def _share(votes: float, valid: float) -> float | None:
    return round(votes / valid, 4) if valid > 0 else None


def detail(
    con: duckdb.DuckDBPyConnection,
    election_id: str,
    contest_id: str,
    geography: str,
    feature_id: str,
) -> dict[str, Any]:
    contest = contest_info(con, election_id, contest_id)
    set_id, retro = geo_set(con, election_id, geography)
    feature = con.execute(
        "SELECT name, jurisdiction FROM features WHERE boundary_set_id = ? AND feature_id = ?",
        [set_id, feature_id],
    ).fetchone()
    if feature is None:
        raise NotFoundError(f"no feature {feature_id!r} in {set_id}")
    votes = dict(
        con.execute(
            "SELECT choice_id, votes FROM geo_results WHERE election_id = ? AND geography = ?"
            " AND contest_id = ? AND feature_id = ?",
            [election_id, geography, contest_id, feature_id],
        ).fetchall()
    )
    valid = sum(votes.get(c["choice_id"], 0.0) for c in contest["choices"] if c["counts"])
    choices = [
        {
            **c,
            "votes": round(float(votes.get(c["choice_id"], 0.0)), 2),
            "share": _share(votes.get(c["choice_id"], 0.0), valid) if c["counts"] else None,
        }
        for c in contest["choices"]
    ]
    return {
        "feature_id": feature_id,
        "name": feature[0],
        "jurisdiction": feature[1],
        "contest": contest["name"],
        "geography": geography,
        "boundary_set_id": set_id,
        "retroactive": retro,
        "on_ballot": bool(votes),
        "valid_votes": round(valid, 2),
        "choices": choices,
        "method": _method(con, election_id, geography, contest_id, feature_id),
        "contributions": _contributions(con, election_id, geography, contest_id, feature_id),
        "turnout": _turnout(con, election_id, geography, feature_id),
        "source_file": contest["source_file"],
        "source_sha256": contest["file_id"],
    }


def _method(con: duckdb.DuckDBPyConnection, e: str, geo: str, c: str, fid: str) -> str | None:
    row = con.execute(
        "SELECT any_value(method) FROM geo_results WHERE election_id = ? AND geography = ?"
        " AND contest_id = ? AND feature_id = ?",
        [e, geo, c, fid],
    ).fetchone()
    return None if row is None else row[0]


def _contributions(
    con: duckdb.DuckDBPyConnection, e: str, geo: str, contest_id: str, fid: str
) -> list[dict[str, Any]]:
    rows = con.execute(
        "SELECT g.precinct_name, g.split_share, g.method, g.weight_basis,"
        " (SELECT sum(r.votes) FROM precinct_results r JOIN choices h USING (choice_id)"
        "   WHERE r.election_id = g.election_id AND r.precinct_name = g.precinct_name"
        "   AND r.contest_id = ? AND h.choice_kind NOT IN ('over', 'under')) AS valid_votes"
        " FROM geo_contributions g WHERE g.election_id = ? AND g.geography = ? AND g.feature_id = ?"
        " ORDER BY g.split_share DESC, g.precinct_name",
        [contest_id, e, geo, fid],
    ).fetchall()
    return [
        {
            "precinct": p,
            "split_share": round(s, 4),
            "method": m,
            "weight_basis": w,
            "precinct_valid_votes": None if v is None else int(v),
        }
        for p, s, m, w, v in rows
    ]


def _turnout(con: duckdb.DuckDBPyConnection, e: str, geo: str, fid: str) -> dict[str, Any] | None:
    row = con.execute(
        "SELECT registered, ballots_cast FROM geo_turnout WHERE election_id = ?"
        " AND geography = ? AND feature_id = ? AND party = 'ALL'",
        [e, geo, fid],
    ).fetchone()
    if row is None:
        return None
    reg, bal = row
    return {
        "registered": None if reg is None else round(reg, 2),
        "ballots_cast": None if bal is None else round(bal, 2),
        "turnout": round(bal / reg, 4) if reg and bal is not None else None,
    }
