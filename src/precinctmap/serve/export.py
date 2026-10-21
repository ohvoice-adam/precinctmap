"""CSV and GeoJSON exports of the current view (election + contest + geography)."""

import csv
import io
import json
from typing import Any

import duckdb

from precinctmap.serve.geo import geojson
from precinctmap.serve.results import results

CSV_COLUMNS = [
    "election_id",
    "contest",
    "geography",
    "feature_id",
    "feature_name",
    "choice",
    "party",
    "votes",
    "share_of_valid_votes",
    "method",
    "precincts_exact",
    "precincts_allocated",
    "boundary_set_id",
    "source_file",
]


def _names(con: duckdb.DuckDBPyConnection, set_id: str) -> dict[str, str]:
    rows = con.execute(
        "SELECT feature_id, name FROM features WHERE boundary_set_id = ?", [set_id]
    ).fetchall()
    return {r[0]: r[1] for r in rows}


def export_rows(
    con: duckdb.DuckDBPyConnection, election_id: str, contest_id: str, geography: str
) -> list[dict[str, Any]]:
    r = results(con, election_id, contest_id, geography)
    names = _names(con, r["boundary_set_id"])
    counted = [i for i, c in enumerate(r["choices"]) if c["counts"]]
    rows = []
    for fid in sorted(r["features"]):
        f = r["features"][fid]
        if f["v"] is None:
            continue  # contest not on this area's ballots
        valid = sum(f["v"][i] for i in counted)
        for i, c in enumerate(r["choices"]):
            share = round(f["v"][i] / valid, 4) if c["counts"] and valid > 0 else None
            rows.append(
                {
                    "election_id": election_id,
                    "contest": r["contest"],
                    "geography": geography,
                    "feature_id": fid,
                    "feature_name": names.get(fid, fid),
                    "choice": c["name"],
                    "party": c["party"],
                    "votes": f["v"][i],
                    "share_of_valid_votes": share,
                    "method": f["method"],
                    "precincts_exact": f["pe"],
                    "precincts_allocated": f["pa"],
                    "boundary_set_id": r["boundary_set_id"],
                    "source_file": r["source_file"],
                }
            )
    return rows


def export_csv(
    con: duckdb.DuckDBPyConnection, election_id: str, contest_id: str, geography: str
) -> str:
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=CSV_COLUMNS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(export_rows(con, election_id, contest_id, geography))
    return buf.getvalue()


def export_geojson(
    con: duckdb.DuckDBPyConnection,
    election_id: str,
    contest_id: str,
    geography: str,
) -> bytes:
    """Boundaries of the view with each area's votes per choice as properties."""
    r = results(con, election_id, contest_id, geography)
    row = con.execute(
        "SELECT county, election_date FROM elections WHERE election_id = ?", [election_id]
    ).fetchone()
    assert row is not None  # results() already proved the election exists
    _, body = geojson(con, geography, row[0], row[1])
    fc = json.loads(body)
    for feature in fc["features"]:
        f = r["features"].get(feature["properties"]["feature_id"])
        props = feature["properties"]
        props.update(contest=r["contest"], method=None, on_ballot=False)
        if f and f["v"] is not None:
            props.update(method=f["method"], on_ballot=True)
            props.update({c["name"]: v for c, v in zip(r["choices"], f["v"], strict=True)})
        props.update(registered=f and f["reg"], ballots_cast=f and f["bal"])
    fc.update(
        election_id=election_id,
        contest=r["contest"],
        source_file=r["source_file"],
        notes=r["notes"],
    )
    return json.dumps(fc, separators=(",", ":")).encode()
