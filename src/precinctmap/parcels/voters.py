"""Registered-voter measures for the property layer, stored in parcel_stats.

Registered voters come from the most recent election whose results file has registration
(precinct_turnout party 'ALL', carried to every geography by geo_turnout: exact where precincts
nest, allocated by 2020 block population where they split). Density divides by each feature's
own land area (area_land: polygon minus TIGER water). Per housing unit divides by the active
parcel file's estimated housing units. `n` is the area's residential parcels, as for every
property measure (areas under LOW_PARCEL_THRESHOLD are hatched).

Elections and parcels have separate dates: the boundary set must match per geography (a
mismatch skips that geography and is logged in parcel_log), and the API names the election.
"""

from dataclasses import dataclass

import duckdb
import pandas as pd

from precinctmap.parcels.areas import GEOGRAPHIES


@dataclass(frozen=True)
class VoterMetric:
    metric: str
    label: str
    kind: str  # 'count' | 'density' | 'ratio'
    description: str


REGISTRATION_NOTE = (
    "Registered voters are from the most recent election's results file, so they count people"
    " registered at that election, not adults or residents."
)

VOTER_METRICS: tuple[VoterMetric, ...] = (
    VoterMetric(
        "registered_voters",
        "Registered voters",
        "count",
        "Registered voters in the most recent election's results file.",
    ),
    VoterMetric(
        "registered_voters_per_sqmi",
        "Registered voters per square mile",
        "density",
        "Registered voters per square mile of land: the area's own boundary minus lakes, ponds"
        " and rivers (Census TIGER area water).",
    ),
    VoterMetric(
        "registered_voters_per_unit",
        "Registered voters per housing unit",
        "ratio",
        "Registered voters / estimated housing units. Not household size: the rolls leave out"
        " noncitizens and unregistered adults and keep some who have moved, and vacant units"
        " count.",
    ),
)
VOTER_IDS = tuple(m.metric for m in VOTER_METRICS)


class VoterStatsError(AssertionError):
    pass


def latest_registration(con: duckdb.DuckDBPyConnection) -> str | None:
    """The most recent election with registered voters, or None."""
    row = con.execute(
        "SELECT e.election_id FROM elections e WHERE EXISTS (SELECT 1 FROM precinct_turnout t"
        " WHERE t.election_id = e.election_id AND t.party = 'ALL' AND t.registered > 0)"
        " ORDER BY e.election_date DESC, e.election_id DESC LIMIT 1"
    ).fetchone()
    return None if row is None else str(row[0])


def _frame(con: duckdb.DuckDBPyConnection, file_id: str, election: str, geo: str) -> pd.DataFrame:
    """One row per feature that has parcels or registered voters (a full outer join, so no area
    drops out): registered, land, units, parcels."""
    return con.execute(
        "WITH p AS (SELECT boundary_set_id, feature_id, value AS units, n FROM parcel_stats"
        "   WHERE file_id = ? AND geography = ? AND metric = 'housing_units'),"
        " r AS (SELECT boundary_set_id, feature_id, registered FROM geo_turnout"
        "   WHERE election_id = ? AND geography = ? AND party = 'ALL')"
        " SELECT coalesce(p.boundary_set_id, r.boundary_set_id) AS boundary_set_id,"
        "   coalesce(p.feature_id, r.feature_id) AS feature_id, r.registered, p.units,"
        "   coalesce(p.n, 0) AS n, l.land_sqmi"
        " FROM p FULL JOIN r USING (boundary_set_id, feature_id)"
        " LEFT JOIN area_land l"
        "   ON l.boundary_set_id = coalesce(p.boundary_set_id, r.boundary_set_id)"
        "   AND l.feature_id = coalesce(p.feature_id, r.feature_id)",
        [file_id, geo, election, geo],
    ).df()


def _sets(con: duckdb.DuckDBPyConnection, sql: str, params: list[str]) -> set[str]:
    return {str(r[0]) for r in con.execute(sql, params).fetchall()}


def _check(con: duckdb.DuckDBPyConnection, election: str, geo: str, frame: pd.DataFrame) -> None:
    """Every registered voter geo_turnout mapped in `geo` is in some row."""
    row = con.execute(
        "SELECT coalesce(sum(registered), 0) FROM geo_turnout"
        " WHERE election_id = ? AND geography = ? AND party = 'ALL'",
        [election, geo],
    ).fetchone()
    want = float(row[0]) if row else 0.0
    got = float(frame["registered"].fillna(0).sum())
    if abs(got - want) > 0.5:
        raise VoterStatsError(f"{geo}: {got:,.1f} registered voters in areas, {want:,.1f} mapped")


def _long(frame: pd.DataFrame, file_id: str, geo: str) -> pd.DataFrame:
    reg = frame["registered"]
    land = frame["land_sqmi"].where(frame["land_sqmi"] > 0)
    units = frame["units"].where(frame["units"] > 0)
    values = {
        "registered_voters": reg,
        "registered_voters_per_sqmi": reg / land,
        "registered_voters_per_unit": reg / units,
    }
    return pd.concat(
        [
            pd.DataFrame(
                {
                    "file_id": file_id,
                    "geography": geo,
                    "boundary_set_id": frame["boundary_set_id"],
                    "feature_id": frame["feature_id"],
                    "metric": metric,
                    "value": v.astype("float64"),
                    "n": frame["n"].astype("int64"),
                }
            )
            for metric, v in values.items()
        ],
        ignore_index=True,
    )


def refresh_voter_stats(con: duckdb.DuckDBPyConnection, file_id: str | None = None) -> int:
    """Replace the voter measures of `file_id` (default: the active parcel file) from the most
    recent election with registration. Returns rows written (0 when nothing to do)."""
    if file_id is None:
        row = con.execute("SELECT file_id FROM parcel_files WHERE status = 'active'").fetchone()
        if row is None:
            return 0
        file_id = str(row[0])
    election = latest_registration(con)
    frames, log = [], []
    if election is not None:
        for geo in GEOGRAPHIES:
            p_sets = _sets(
                con,
                "SELECT DISTINCT boundary_set_id FROM parcel_stats WHERE file_id = ?"
                " AND geography = ?",
                [file_id, geo],
            )
            r_sets = _sets(
                con,
                "SELECT DISTINCT boundary_set_id FROM geo_turnout WHERE election_id = ?"
                " AND geography = ?",
                [election, geo],
            )
            if p_sets and r_sets and p_sets != r_sets:
                log.append(
                    (f"{geo}_registration_set_differs", f"parcels {p_sets}, {election} {r_sets}")
                )
                continue
            frame = _frame(con, file_id, election, geo)
            _check(con, election, geo, frame)
            no_land = int((frame["registered"].notna() & frame["land_sqmi"].isna()).sum())
            if no_land:
                log.append((f"{geo}_no_land_area", f"{no_land} areas lack area_land rows"))
            frames.append(_long(frame, file_id, geo))
    return _write(con, file_id, election, frames, log)


def _write(
    con: duckdb.DuckDBPyConnection,
    file_id: str,
    election: str | None,
    frames: list[pd.DataFrame],
    log: list[tuple[str, str]],
) -> int:
    ids = ", ".join(f"'{m}'" for m in VOTER_IDS)
    con.execute("BEGIN")
    try:
        con.execute(f"DELETE FROM parcel_stats WHERE file_id = ? AND metric IN ({ids})", [file_id])
        con.execute("DELETE FROM parcel_registration WHERE file_id = ?", [file_id])
        con.execute(
            "DELETE FROM parcel_log WHERE file_id = ? AND issue LIKE '%registration%'", [file_id]
        )
        con.execute(
            "DELETE FROM parcel_log WHERE file_id = ? AND issue LIKE '%no_land_area'", [file_id]
        )
        rows = 0
        if frames:
            stats = pd.concat(frames, ignore_index=True)
            con.register("_vs", stats)
            con.execute("INSERT INTO parcel_stats BY NAME SELECT * FROM _vs")
            con.unregister("_vs")
            rows = len(stats)
            con.execute(
                "INSERT INTO parcel_registration (file_id, election_id) VALUES (?, ?)",
                [file_id, election],
            )
        for issue, detail in log:
            con.execute(
                "INSERT INTO parcel_log (file_id, pid, issue, detail) VALUES (?, NULL, ?, ?)",
                [file_id, issue, detail],
            )
        con.execute("COMMIT")
    except Exception:
        con.execute("ROLLBACK")
        raise
    return rows
