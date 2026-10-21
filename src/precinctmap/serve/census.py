"""Census demographics for the map (latest ACS release): catalog, stats, detail, CSV."""

import csv
import io
from typing import Any

import duckdb

from precinctmap.census.tables import BY_ID, MEASURES, level_of
from precinctmap.serve.labels import GEOGRAPHY_LABELS, NOT_IN_COLUMBUS, ZCTA_NOTE
from precinctmap.serve.results import NotFoundError

ACS_NOTE = (
    "American Community Survey 5-year estimates: survey estimates pooled over five years, with "
    "90% margins of error (±). Block-group estimates are split across 2020 census blocks by "
    "population (or housing units, for households) and summed into each area, so values for "
    "small areas are approximate."
)
RELIABILITY = (
    "Hatched areas have a large margin of error (coefficient of variation above 30%): read "
    "them with care."
)
TRACT_NOTE = (
    "Place of birth and citizenship are published only for census tracts, so these values are "
    "smoothed across each tract."
)
COUNCIL_NOTE = "Council districts count only blocks in Columbus precincts."
ORDER = ["precinct", "council_district", "municipality", "zcta"]


def _active(con: duckdb.DuckDBPyConnection) -> tuple[str, str, Any] | None:
    row = con.execute(
        "SELECT release_id, label, as_of FROM census_releases ORDER BY year_end DESC LIMIT 1"
    ).fetchone()
    return None if row is None else (str(row[0]), str(row[1]), row[2])


def _require(con: duckdb.DuckDBPyConnection) -> tuple[str, str, Any]:
    active = _active(con)
    if active is None:
        raise NotFoundError("no census release is loaded")
    return active


def _files(con: duckdb.DuckDBPyConnection, release: str) -> dict[str, tuple[str, str]]:
    rows = con.execute(
        "SELECT table_id, filename, sha256 FROM census_files WHERE release_id = ?", [release]
    ).fetchall()
    return {t: (f, s) for t, f, s in rows}


def census_catalog(con: duckdb.DuckDBPyConnection) -> dict[str, Any] | None:
    active = _active(con)
    if active is None:
        return None
    release, label, as_of = active
    geos = {
        g
        for (g,) in con.execute(
            "SELECT DISTINCT geography FROM census_stats WHERE release_id = ?", [release]
        ).fetchall()
    }
    return {
        "dataset": "census",
        "label": f"Census demographics ({label.removesuffix(' estimates')})",
        "as_of": as_of.isoformat(),
        "source_file": f"{label}, summary file ({len(_files(con, release))} tables)",
        "geographies": [{"geography": g, "label": GEOGRAPHY_LABELS[g]} for g in ORDER if g in geos],
        "metrics": [
            {
                "metric": m.metric,
                "label": m.label,
                "kind": m.kind,
                "description": m.description,
                "group": m.group,
                "universe": m.universe,
            }
            for m in MEASURES
        ],
        "notes": [ACS_NOTE, RELIABILITY],
    }


def _notes(metric: str, geography: str) -> list[str]:
    notes = [ACS_NOTE, RELIABILITY]
    if level_of(BY_ID[metric].table) == "tract":
        notes.append(TRACT_NOTE)
    if geography == "council_district":
        notes += [NOT_IN_COLUMBUS, COUNCIL_NOTE]
    if geography == "zcta":
        notes.append(ZCTA_NOTE)
    return notes


def _value(v: float | None, kind: str) -> float | None:
    if v is None:
        return None
    return round(float(v), 4 if kind == "share" else 1)


def census_stats(con: duckdb.DuckDBPyConnection, metric: str, geography: str) -> dict[str, Any]:
    m = BY_ID.get(metric)
    if m is None:
        raise NotFoundError(f"unknown census metric {metric!r}")
    release, label, as_of = _require(con)
    rows = con.execute(
        "SELECT boundary_set_id, feature_id, value, moe, base, reliable FROM census_stats"
        " WHERE release_id = ? AND geography = ? AND metric = ?",
        [release, geography, metric],
    ).fetchall()
    if not rows:
        raise NotFoundError(f"no census statistics for {geography!r}")
    filename, _ = _files(con, release).get(m.table, ("", ""))
    return {
        "dataset": "census",
        "metric": m.metric,
        "label": m.label,
        "kind": m.kind,
        "description": m.description,
        "universe": m.universe,
        "geography": geography,
        "geography_label": GEOGRAPHY_LABELS[geography],
        "boundary_set_id": rows[0][0],
        "as_of": as_of.isoformat(),
        "source_file": f"{label}, {m.table} ({filename})",
        "notes": _notes(metric, geography),
        "features": {
            fid: {
                "value": _value(v, m.kind),
                "n": round(base or 0),
                "moe": _value(e, m.kind),
                "reliable": bool(ok),
            }
            for _, fid, v, e, base, ok in rows
        },
    }


def census_detail(con: duckdb.DuckDBPyConnection, geography: str, feature: str) -> dict[str, Any]:
    release, label, as_of = _require(con)
    rows = {
        r[0]: r[1:]
        for r in con.execute(
            "SELECT metric, value, moe, base, reliable, boundary_set_id FROM census_stats"
            " WHERE release_id = ? AND geography = ? AND feature_id = ?",
            [release, geography, feature],
        ).fetchall()
    }
    if not rows:
        raise NotFoundError(f"no census statistics for {geography} {feature!r}")
    set_id = next(iter(rows.values()))[4]
    name = con.execute(
        "SELECT name FROM features WHERE boundary_set_id = ? AND feature_id = ?", [set_id, feature]
    ).fetchone()
    files = _files(con, release)
    return {
        "dataset": "census",
        "feature_id": feature,
        "name": name[0] if name else feature,
        "geography": geography,
        "as_of": as_of.isoformat(),
        "source_file": f"{label} summary file: "
        + ", ".join(f"{t} ({f}, sha256 {s[:12]})" for t, (f, s) in sorted(files.items())),
        "metrics": [
            {
                "metric": m.metric,
                "label": m.label,
                "kind": m.kind,
                "universe": m.universe,
                "value": _value(rows[m.metric][0], m.kind),
                "moe": _value(rows[m.metric][1], m.kind),
                "n": round(rows[m.metric][2] or 0),
                "reliable": bool(rows[m.metric][3]),
            }
            for m in MEASURES
            if m.metric in rows
        ],
        "grades": [],
    }


def census_export_csv(con: duckdb.DuckDBPyConnection, geography: str) -> str:
    release, label, as_of = _require(con)
    rows = con.execute(
        "SELECT s.feature_id, f.name, s.metric, s.value, s.moe, s.base, s.reliable"
        " FROM census_stats s LEFT JOIN features f ON f.boundary_set_id = s.boundary_set_id"
        " AND f.feature_id = s.feature_id WHERE s.release_id = ? AND s.geography = ?"
        " ORDER BY 1, 3",
        [release, geography],
    ).fetchall()
    files = _files(con, release)
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(
        ["geography", "feature_id", "feature_name", "metric", "label", "value", "moe_90",
         "base", "universe", "reliable", "release", "boundaries_as_of", "source_table",
         "source_file"]
    )  # fmt: skip
    for fid, name, metric, value, moe, base, ok in rows:
        m = BY_ID[metric]
        w.writerow(
            [geography, fid, name or fid, metric, m.label, value, moe, base, m.universe, ok,
             label, as_of.isoformat(), m.table, files.get(m.table, ("", ""))[0]]
        )  # fmt: skip
    return buf.getvalue()
