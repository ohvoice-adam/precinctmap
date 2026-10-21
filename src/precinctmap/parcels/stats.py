"""Residential property statistics per area, materialized into parcel_stats.

Universe: residential parcels (class R with a dwelling, plus apartment buildings: class C,
land use 401-403). Valuation and grade statistics cover class R homes only (one building
value for a 200-unit complex is not a home value). Each parcel counts in the area its point
(or voter-file precinct) puts it in, for every geography, so medians are exact. Valuation
statistics skip zero values (exempt or abated parcels carry 0 in APPRBLD/APPRTOT); `n`
records how many parcels each value rests on.
"""

from dataclasses import dataclass

import duckdb
import pandas as pd


@dataclass(frozen=True)
class Metric:
    metric: str
    label: str
    kind: str  # 'count' | 'share' | 'currency' | 'currency_delta' | 'score'
    value_sql: str
    n_sql: str
    description: str


_ALL = "count(*)"
_BLD = "count(*) FILTER (WHERE building_value > 0)"
_TOT = "count(*) FILTER (WHERE appraised_total > 0)"
_GRD = "count(grade_score)"


def _m(metric: str, label: str, kind: str, value: str, n: str, description: str) -> Metric:
    return Metric(metric, label, kind, value, n, description)


_RENT = "count(*) FILTER (WHERE likely_rental)"
_UNITS_RENT = "sum(units_estimate) FILTER (WHERE likely_rental)"
_BV = "FILTER (WHERE building_value > 0)"
_TV = "FILTER (WHERE appraised_total > 0)"
_RENTAL_DEF = (
    "Apartment buildings, or the owner's name contains LLC, or the owner's address differs"
    " from the parcel's."
)
_SKEW = "Positive when a few high values pull the mean above the typical home."

METRICS: tuple[Metric, ...] = (
    _m(
        "residential_parcels",
        "Residential parcels",
        "count",
        "count(*)",
        _ALL,
        "Homes (class R with a dwelling) plus apartment buildings.",
    ),
    _m(
        "apartment_buildings",
        "Apartment buildings (4+ units)",
        "count",
        "count(*) FILTER (WHERE apartment)",
        _ALL,
        "Auditor land use 401, 402, or 403.",
    ),
    _m(
        "housing_units",
        "Housing units (estimated)",
        "count",
        "sum(units_estimate)",
        _ALL,
        "1 per home or condo, 2 per two-family, 3 per three-family; apartment units from"
        " voter-file unit numbers within each land-use class's range.",
    ),
    _m("likely_rentals", "Likely rental parcels", "count", _RENT, _ALL, _RENTAL_DEF),
    _m(
        "likely_rental_share",
        "Likely rental parcels, share",
        "share",
        "avg(likely_rental::INTEGER)",
        _ALL,
        "Likely rental parcels / residential parcels.",
    ),
    _m(
        "likely_rental_units",
        "Likely rental units (estimated)",
        "count",
        _UNITS_RENT,
        _ALL,
        "Estimated units in likely-rental parcels (every apartment unit counts).",
    ),
    _m(
        "likely_rental_unit_share",
        "Likely rental units, share of units",
        "share",
        f"{_UNITS_RENT} / nullif(sum(units_estimate), 0)",
        _ALL,
        "Likely rental units / estimated housing units.",
    ),
    _m(
        "llc_owned",
        "Owned by an LLC",
        "count",
        "count(*) FILTER (WHERE owner_llc)",
        _ALL,
        "Owner name contains LLC.",
    ),
    _m(
        "owner_elsewhere",
        "Owner's address is elsewhere",
        "count",
        "count(*) FILTER (WHERE owner_address_differs)",
        _ALL,
        "Owner's address differs from the parcel's (house number or ZIP).",
    ),
    _m(
        "median_building_value",
        "Median building value",
        "currency",
        f"median(building_value) {_BV}",
        _BLD,
        "Auditor appraised building value (APPRBLD) of homes, above 0.",
    ),
    _m(
        "mean_building_value",
        "Mean building value",
        "currency",
        f"avg(building_value) {_BV}",
        _BLD,
        "As above, mean.",
    ),
    _m(
        "building_value_mean_minus_median",
        "Building value: mean minus median",
        "currency_delta",
        f"avg(building_value) {_BV} - median(building_value) {_BV}",
        _BLD,
        _SKEW,
    ),
    _m(
        "median_total_value",
        "Median total value",
        "currency",
        f"median(appraised_total) {_TV}",
        _TOT,
        "Auditor appraised total value, land and building (APPRTOT), of homes, above 0.",
    ),
    _m(
        "mean_total_value",
        "Mean total value",
        "currency",
        f"avg(appraised_total) {_TV}",
        _TOT,
        "As above, mean.",
    ),
    _m(
        "total_value_mean_minus_median",
        "Total value: mean minus median",
        "currency_delta",
        f"avg(appraised_total) {_TV} - median(appraised_total) {_TV}",
        _TOT,
        _SKEW,
    ),
    _m(
        "mean_grade_score",
        "Construction grade (mean score)",
        "score",
        "avg(grade_score)",
        _GRD,
        "Auditor building grade of homes: A = 5 down to E = 1; each + or - step is 0.2.",
    ),
    _m(
        "grade_d_or_below_share",
        "Grade D or E, share",
        "share",
        "avg((grade_score < 2.5)::INTEGER)",
        _GRD,
        "Share of graded homes at D+2 or below.",
    ),
    _m(
        "grade_b_or_above_share",
        "Grade B or above, share",
        "share",
        "avg((grade_score > 3.5)::INTEGER)",
        _GRD,
        "Share of graded homes at B-2 or above.",
    ),
)
BY_ID = {m.metric: m for m in METRICS}

# geography -> (set column, feature column) in parcel_assignments
GEOGRAPHY_COLUMNS = {
    "precinct": ("precinct_set_id", "precinct_name"),
    "council_district": ("council_set_id", "council_district"),
    "municipality": ("municipality_set_id", "municipality"),
    "zcta": ("zcta_set_id", "zcta"),
}


def _wide(con: duckdb.DuckDBPyConnection, file_id: str, geo: str) -> pd.DataFrame:
    set_col, feat_col = GEOGRAPHY_COLUMNS[geo]
    cols = ", ".join(f"{m.value_sql} AS v_{m.metric}, {m.n_sql} AS n_{m.metric}" for m in METRICS)
    return con.execute(
        f"SELECT a.{set_col} AS boundary_set_id, a.{feat_col} AS feature_id, {cols}"
        " FROM (SELECT * REPLACE ("
        "   CASE WHEN apartment THEN NULL ELSE building_value END AS building_value,"
        "   CASE WHEN apartment THEN NULL ELSE appraised_total END AS appraised_total)"
        "   FROM parcels) p JOIN parcel_assignments a USING (file_id, pid)"
        f" WHERE p.file_id = ? AND p.residential AND a.{feat_col} IS NOT NULL"
        " GROUP BY ALL",
        [file_id],
    ).df()


def materialize_stats(con: duckdb.DuckDBPyConnection, file_id: str) -> int:
    """Replace parcel_stats for `file_id`; returns rows written."""
    frames = []
    for geo in GEOGRAPHY_COLUMNS:
        wide = _wide(con, file_id, geo)
        for m in METRICS:
            frames.append(
                pd.DataFrame(
                    {
                        "file_id": file_id,
                        "geography": geo,
                        "boundary_set_id": wide["boundary_set_id"],
                        "feature_id": wide["feature_id"],
                        "metric": m.metric,
                        "value": wide[f"v_{m.metric}"].astype("float64"),
                        "n": wide[f"n_{m.metric}"].astype("int64"),
                    }
                )
            )
    long = pd.concat(frames, ignore_index=True)
    _assert_totals(con, file_id, long)
    con.execute("BEGIN")
    try:
        con.execute("DELETE FROM parcel_stats WHERE file_id = ?", [file_id])
        con.register("_ps", long)
        con.execute("INSERT INTO parcel_stats BY NAME SELECT * FROM _ps")
        con.unregister("_ps")
        con.execute("COMMIT")
    except Exception:
        con.execute("ROLLBACK")
        raise
    return len(long)


class StatsTotalsError(AssertionError):
    pass


def _assert_totals(con: duckdb.DuckDBPyConnection, file_id: str, long: pd.DataFrame) -> None:
    """Every residential parcel counts once per geography (council: once if in Columbus)."""
    expected = con.execute(
        "SELECT count(*), count(*) FILTER (WHERE a.council_district IS NOT NULL)"
        " FROM parcels p JOIN parcel_assignments a USING (file_id, pid)"
        " WHERE p.file_id = ? AND p.residential",
        [file_id],
    ).fetchone()
    assert expected is not None
    homes = long[long["metric"] == "residential_parcels"].groupby("geography")["value"].sum()
    for geo, total in homes.items():
        want = expected[1] if geo == "council_district" else expected[0]
        if int(total) != want:
            raise StatsTotalsError(
                f"{geo}: {int(total):,} residential parcels in areas, {want:,} expected"
            )
