"""Residential property statistics for the map (active auditor parcel file)."""

import csv
import io
from typing import Any

import duckdb

from precinctmap.parcels.stats import BY_ID, GEOGRAPHY_COLUMNS, METRICS
from precinctmap.serve.labels import GEOGRAPHY_LABELS, NOT_IN_COLUMBUS, ZCTA_NOTE
from precinctmap.serve.results import NotFoundError

UNIVERSE = (
    "Residential parcels: auditor class R with a dwelling, plus apartment buildings (classed "
    "commercial, land use 401-403). Valuation and grade measures cover class R homes only."
)
RENTAL = (
    "Likely rental: an apartment building, or the owner's name contains LLC, or the owner's "
    "address differs from the parcel's (house number or ZIP). Housing units are estimates."
)
CONDITION = "Building condition (COND) is blank in this auditor file, so it cannot be mapped."


def _active(con: duckdb.DuckDBPyConnection) -> tuple[str, str, Any] | None:
    row = con.execute(
        "SELECT file_id, filename, as_of FROM parcel_files WHERE status = 'active'"
    ).fetchone()
    return None if row is None else (str(row[0]), str(row[1]), row[2])


def property_catalog(con: duckdb.DuckDBPyConnection) -> dict[str, Any] | None:
    active = _active(con)
    if active is None:
        return None
    file_id, filename, as_of = active
    geos = [
        g
        for (g,) in con.execute(
            "SELECT DISTINCT geography FROM parcel_stats WHERE file_id = ?", [file_id]
        ).fetchall()
    ]
    order = ["precinct", "council_district", "municipality", "zcta"]
    return {
        "as_of": as_of.isoformat(),
        "source_file": filename,
        "geographies": [{"geography": g, "label": GEOGRAPHY_LABELS[g]} for g in order if g in geos],
        "metrics": [
            {"metric": m.metric, "label": m.label, "kind": m.kind, "description": m.description}
            for m in METRICS
        ],
        "notes": [UNIVERSE, RENTAL, CONDITION],
    }


def _require(con: duckdb.DuckDBPyConnection) -> tuple[str, str, Any]:
    active = _active(con)
    if active is None:
        raise NotFoundError("no parcel file is loaded")
    return active


def property_stats(con: duckdb.DuckDBPyConnection, metric: str, geography: str) -> dict[str, Any]:
    m = BY_ID.get(metric)
    if m is None:
        raise NotFoundError(f"unknown property metric {metric!r}")
    file_id, filename, as_of = _require(con)
    rows = con.execute(
        "SELECT boundary_set_id, feature_id, value, n FROM parcel_stats"
        " WHERE file_id = ? AND geography = ? AND metric = ?",
        [file_id, geography, metric],
    ).fetchall()
    if not rows:
        raise NotFoundError(f"no property statistics for {geography!r}")
    rental = "rental" in metric or "unit" in metric or metric in ("llc_owned", "owner_elsewhere")
    notes = [UNIVERSE] + ([RENTAL] if rental else [])
    if geography == "council_district":
        notes.append(NOT_IN_COLUMBUS)
    if geography == "zcta":
        notes.append(ZCTA_NOTE)
    return {
        "metric": m.metric,
        "label": m.label,
        "kind": m.kind,
        "description": m.description,
        "geography": geography,
        "geography_label": GEOGRAPHY_LABELS[geography],
        "boundary_set_id": rows[0][0],
        "as_of": as_of.isoformat(),
        "source_file": filename,
        "notes": notes,
        "features": {
            fid: {"value": None if v is None else round(float(v), 4), "n": int(n)}
            for _, fid, v, n in rows
        },
    }


def property_detail(con: duckdb.DuckDBPyConnection, geography: str, feature: str) -> dict[str, Any]:
    file_id, filename, as_of = _require(con)
    rows = dict(
        (r[0], (r[1], r[2]))
        for r in con.execute(
            "SELECT metric, value, n FROM parcel_stats WHERE file_id = ? AND geography = ?"
            " AND feature_id = ?",
            [file_id, geography, feature],
        ).fetchall()
    )
    if not rows:
        raise NotFoundError(f"no residential parcels in {geography} {feature!r}")
    set_id = con.execute(
        "SELECT boundary_set_id FROM parcel_stats WHERE file_id = ? AND geography = ? LIMIT 1",
        [file_id, geography],
    ).fetchone()
    name = con.execute(
        "SELECT name FROM features WHERE boundary_set_id = ? AND feature_id = ?",
        [set_id[0] if set_id else "", feature],
    ).fetchone()
    grades = _grades(con, file_id, geography, feature)
    return {
        "feature_id": feature,
        "name": name[0] if name else feature,
        "geography": geography,
        "as_of": as_of.isoformat(),
        "source_file": filename,
        "metrics": [
            {
                "metric": m.metric,
                "label": m.label,
                "kind": m.kind,
                "value": rows[m.metric][0],
                "n": rows[m.metric][1],
            }
            for m in METRICS
            if m.metric in rows
        ],
        "grades": [{"grade": g, "parcels": int(n)} for g, n in grades],
    }


def _grades(
    con: duckdb.DuckDBPyConnection, file_id: str, geography: str, feature: str
) -> list[tuple[str, int]]:
    """Residential parcels by grade letter in one area."""
    col = GEOGRAPHY_COLUMNS[geography][1]
    rows: list[tuple[str, int]] = con.execute(
        "SELECT CASE WHEN coalesce(p.grade, '') = '' THEN 'Ungraded'"
        " WHEN left(p.grade, 1) IN ('A', 'B', 'C', 'D', 'E') THEN left(p.grade, 1)"
        " ELSE 'Other (S/X, not scored)' END g, count(*) FROM parcels p"
        " JOIN parcel_assignments a USING (file_id, pid) WHERE p.file_id = ? AND p.residential"
        f" AND a.{col} = ? GROUP BY 1 ORDER BY 1",
        [file_id, feature],
    ).fetchall()
    return rows


def property_export_csv(con: duckdb.DuckDBPyConnection, geography: str) -> str:
    file_id, filename, as_of = _require(con)
    rows = con.execute(
        "SELECT s.feature_id, f.name, s.metric, s.value, s.n FROM parcel_stats s"
        " LEFT JOIN features f ON f.boundary_set_id = s.boundary_set_id"
        " AND f.feature_id = s.feature_id WHERE s.file_id = ? AND s.geography = ?"
        " ORDER BY 1, 3",
        [file_id, geography],
    ).fetchall()
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(
        [
            "geography",
            "feature_id",
            "feature_name",
            "metric",
            "label",
            "value",
            "n",
            "as_of",
            "source_file",
        ]
    )
    for fid, name, metric, value, n in rows:
        w.writerow(
            [
                geography,
                fid,
                name or fid,
                metric,
                BY_ID[metric].label,
                value,
                n,
                as_of.isoformat(),
                filename,
            ]
        )
    return buf.getvalue()
