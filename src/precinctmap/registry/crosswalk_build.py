"""Build and store crosswalks for every (precinct set, target set) pair whose validity overlaps."""

import logging
from datetime import date

import duckdb
import pandas as pd

from precinctmap.registry.config import RegistryConfig
from precinctmap.registry.crosswalk import CrosswalkSummary, compute_crosswalk

log = logging.getLogger(__name__)

TARGET_GEOGRAPHIES = ("council_district", "municipality", "zcta")
_CROSSWALK_COLS = [
    "precinct_set_id",
    "target_set_id",
    "precinct_name",
    "feature_id",
    "pop_share",
    "area_share",
    "split_share",
    "method",
    "weight_basis",
]


def _overlaps(a: tuple[date, date | None], b: tuple[date, date | None]) -> bool:
    a_from, a_to = a
    b_from, b_to = b
    return (b_to is None or a_from < b_to) and (a_to is None or b_from < a_to)


def crosswalk_pairs(con: duckdb.DuckDBPyConnection, county: str) -> list[tuple[str, str, str]]:
    """(precinct_set_id, target_set_id, geography) for every overlapping pair.

    A municipality set pairs only with the precinct set it was derived from.
    """
    sets = con.execute(
        "SELECT boundary_set_id, geography, valid_from, valid_to, derived_from FROM boundary_sets"
        " WHERE county = ? ORDER BY boundary_set_id",
        [county],
    ).fetchall()
    precincts = [s for s in sets if s[1] == "precinct"]
    pairs = []
    for p_id, _, p_from, p_to, _ in precincts:
        for t_id, geo, t_from, t_to, parent in sets:
            if geo not in TARGET_GEOGRAPHIES or not _overlaps((p_from, p_to), (t_from, t_to)):
                continue
            if geo == "municipality" and parent != p_id:
                continue
            pairs.append((p_id, t_id, geo))
    return pairs


def write_crosswalk(con: duckdb.DuckDBPyConnection, s: CrosswalkSummary) -> None:
    rows = pd.DataFrame(s.rows, columns=_CROSSWALK_COLS[2:])
    rows.insert(0, "target_set_id", s.target_set_id)
    rows.insert(0, "precinct_set_id", s.precinct_set_id)
    logs = pd.DataFrame(s.log, columns=["precinct_name", "issue", "detail"])
    logs.insert(0, "target_set_id", s.target_set_id)
    logs.insert(0, "precinct_set_id", s.precinct_set_id)
    con.execute("BEGIN")
    try:
        for table in ("precinct_crosswalk", "crosswalk_log"):
            con.execute(
                f"DELETE FROM {table} WHERE precinct_set_id = ? AND target_set_id = ?",
                [s.precinct_set_id, s.target_set_id],
            )
        con.register("_xw", rows)
        con.execute(f"INSERT INTO precinct_crosswalk SELECT {', '.join(_CROSSWALK_COLS)} FROM _xw")
        con.unregister("_xw")
        con.register("_xl", logs)
        con.execute("INSERT INTO crosswalk_log SELECT * FROM _xl")
        con.unregister("_xl")
        _assert_shares_sum_to_one(con, s)
        con.execute("COMMIT")
    except Exception:
        con.execute("ROLLBACK")
        raise


def _assert_shares_sum_to_one(con: duckdb.DuckDBPyConnection, s: CrosswalkSummary) -> None:
    bad = con.execute(
        "SELECT precinct_name, sum(split_share) AS t FROM precinct_crosswalk"
        " WHERE precinct_set_id = ? AND target_set_id = ? GROUP BY 1 HAVING abs(t - 1) > 1e-9",
        [s.precinct_set_id, s.target_set_id],
    ).fetchall()
    if bad:
        raise RuntimeError(f"{s.target_set_id}: split shares do not sum to 1 for {bad[:5]}")


def build_crosswalks(con: duckdb.DuckDBPyConnection, cfg: RegistryConfig) -> list[CrosswalkSummary]:
    out = []
    for p_id, t_id, geo in crosswalk_pairs(con, cfg.county):
        s = compute_crosswalk(con, p_id, t_id, geo, cfg.county, cfg.blocks.vintage)
        write_crosswalk(con, s)
        log.info(
            "crosswalk %s -> %s: %d exact, %d allocated, %d excluded, %d no overlap",
            p_id,
            t_id,
            s.exact,
            s.allocated,
            s.excluded,
            s.no_overlap,
        )
        out.append(s)
    return out
