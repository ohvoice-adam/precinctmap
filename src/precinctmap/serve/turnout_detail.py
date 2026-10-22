"""Turnout detail for one area and the turnout CSV export (see serve/turnout.py)."""

import csv
import io
from typing import Any

import duckdb

from precinctmap.serve.results import NotFoundError, geo_set
from precinctmap.serve.turnout import PARTY_LABELS, _methods, _parties, _source


def _two(x: float | None) -> float | None:
    return None if x is None else round(x, 2)


def _pct(part: float | None, whole: float | None) -> float | None:
    return round(part / whole, 4) if part is not None and whole else None


def _area(
    con: duckdb.DuckDBPyConnection, e: str, geo: str, fid: str
) -> dict[str, tuple[float | None, float | None]]:
    """party -> (registered, ballots_cast) for one feature; 'ALL' is everyone."""
    return {
        p: (reg, bal)
        for p, reg, bal in con.execute(
            "SELECT party, registered, ballots_cast FROM geo_turnout WHERE election_id = ?"
            " AND geography = ? AND feature_id = ?",
            [e, geo, fid],
        ).fetchall()
    }


def _contributions(
    con: duckdb.DuckDBPyConnection, e: str, geo: str, fid: str
) -> list[dict[str, Any]]:
    rows = con.execute(
        "SELECT g.precinct_name, g.split_share, g.method, g.weight_basis, t.ballots_cast"
        " FROM geo_contributions g LEFT JOIN precinct_turnout t ON t.election_id = g.election_id"
        " AND t.precinct_name = g.precinct_name AND t.party = 'ALL'"
        " WHERE g.election_id = ? AND g.geography = ? AND g.feature_id = ?"
        " ORDER BY g.split_share DESC, g.precinct_name",
        [e, geo, fid],
    ).fetchall()
    return [
        {"precinct": p, "split_share": round(s, 4), "method": m, "weight_basis": w,
         "precinct_ballots": None if b is None else int(b)}
        for p, s, m, w, b in rows
    ]  # fmt: skip


def turnout_detail(
    con: duckdb.DuckDBPyConnection, election_id: str, geography: str, feature_id: str
) -> dict[str, Any]:
    set_id, retro = geo_set(con, election_id, geography)
    feature = con.execute(
        "SELECT name, jurisdiction FROM features WHERE boundary_set_id = ? AND feature_id = ?",
        [set_id, feature_id],
    ).fetchone()
    if feature is None:
        raise NotFoundError(f"no feature {feature_id!r} in {set_id}")
    area = _area(con, election_id, geography, feature_id)
    reg, bal = area.get("ALL", (None, None))
    parties = [
        {
            "party": p,
            "label": PARTY_LABELS.get(p, f"{p} ballots"),
            "ballots": None if area.get(p) is None else round(float(area[p][1] or 0), 2),
            "of_registered": _pct(area.get(p, (None, None))[1], reg),
            "of_ballots": _pct(area.get(p, (None, None))[1], bal),
        }
        for p in _parties(con, election_id)
    ]
    filename, sha = _source(con, election_id)
    return {
        "feature_id": feature_id,
        "name": feature[0],
        "jurisdiction": feature[1],
        "geography": geography,
        "boundary_set_id": set_id,
        "retroactive": retro,
        "registered": None if reg is None else round(reg, 2),
        "ballots_cast": None if bal is None else round(bal, 2),
        "turnout": _pct(bal, reg),
        "parties": parties,
        "method": _methods(con, election_id, geography).get(feature_id, (None, 0, 0))[0],
        "contributions": _contributions(con, election_id, geography, feature_id),
        "source_file": filename,
        "source_sha256": sha,
    }


def turnout_export_csv(con: duckdb.DuckDBPyConnection, election_id: str, geography: str) -> str:
    set_id, _ = geo_set(con, election_id, geography)
    parties = _parties(con, election_id)
    names = dict(
        con.execute(
            "SELECT feature_id, name FROM features WHERE boundary_set_id = ?", [set_id]
        ).fetchall()
    )
    methods = _methods(con, election_id, geography)
    rows: dict[str, dict[str, tuple[float | None, float | None]]] = {}
    for fid, p, reg, bal in con.execute(
        "SELECT feature_id, party, registered, ballots_cast FROM geo_turnout"
        " WHERE election_id = ? AND geography = ? ORDER BY feature_id",
        [election_id, geography],
    ).fetchall():
        rows.setdefault(fid, {})[p] = (reg, bal)
    filename, _ = _source(con, election_id)
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    party_cols = [
        f"{p.lower()}_{k}"
        for p in parties
        for k in ("ballots", "pct_of_registered", "pct_of_ballots")
    ]
    head = ["election_id", "geography", "feature_id", "feature_name", "registered", "ballots_cast"]
    w.writerow([*head, "turnout", *party_cols, "method", "source_file"])
    for fid, area in rows.items():
        reg, bal = area.get("ALL", (None, None))
        party_vals: list[object] = []
        for p in parties:
            pb = area.get(p, (None, None))[1]
            party_vals += [_two(pb), _pct(pb, reg), _pct(pb, bal)]
        method = methods.get(fid, (None, 0, 0))[0]
        ids = [election_id, geography, fid, names.get(fid, fid)]
        w.writerow([*ids, _two(reg), _two(bal), _pct(bal, reg), *party_vals, method, filename])
    return buf.getvalue()
