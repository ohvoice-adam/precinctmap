"""Precinct -> target-unit crosswalks weighted by 2020 census block population.

For each precinct: pieces = precinct ∩ unit; piece population = sum of block pop * (block ∩ piece
area / block area). Shares are renormalized over the units the precinct touches (residual
outside every unit is logged). If one unit holds >= NEST_TOLERANCE of the precinct, the
precinct nests: one 'exact' row with split_share 1. Otherwise 'allocated' rows. Precincts with
no population fall back to area. Council districts only take Columbus precincts.
"""

from dataclasses import dataclass, field

import duckdb
import geopandas as gpd
import pandas as pd

from precinctmap.registry.blocks import read_blocks
from precinctmap.registry.store import read_features

NEST_TOLERANCE = 0.99
MIN_SHARE = 0.001  # pieces below this share are slivers: dropped and logged, rest renormalized
AREA_CRS = 3735  # Ohio South, US feet


@dataclass
class CrosswalkSummary:
    precinct_set_id: str
    target_set_id: str
    eligible: int = 0
    excluded: int = 0
    exact: int = 0
    allocated: int = 0
    no_overlap: int = 0
    log: list[tuple[str, str, str]] = field(default_factory=list)  # (precinct, issue, detail)
    rows: list[dict[str, object]] = field(default_factory=list)


def _population(blocks: gpd.GeoDataFrame, zones: gpd.GeoDataFrame, keys: list[str]) -> pd.Series:
    """Block population falling in each zone, split by block area share."""
    b = blocks.assign(block_area=blocks.area)
    pieces = gpd.overlay(b, zones[[*keys, "geometry"]], how="intersection", keep_geom_type=True)
    pieces["pop_part"] = pieces["pop"] * pieces.area / pieces["block_area"]
    return pd.Series(pieces.groupby(keys)["pop_part"].sum())


def _eligible(
    precincts: gpd.GeoDataFrame, targets: gpd.GeoDataFrame, geography: str, s: CrosswalkSummary
) -> gpd.GeoDataFrame:
    if geography != "council_district":
        return precincts
    juris = set(targets["jurisdiction"].dropna())
    keep = precincts["jurisdiction"].isin(juris)
    for name in precincts.loc[~keep, "precinct_name"]:
        s.log.append((name, "excluded", f"not in {', '.join(sorted(juris))}"))
    s.excluded = int((~keep).sum())
    return precincts.loc[keep]


def _decide(
    name: str, shares: pd.DataFrame, basis: str, geography: str, s: CrosswalkSummary
) -> None:
    """shares: feature_id, share (raw), pop_share, area_share for one precinct."""
    inside = float(shares["share"].sum())
    if inside < 1 - 1e-3:
        s.log.append(
            (name, "outside_units", f"{1 - inside:.2%} of {basis} outside every unit; renormalized")
        )
    norm = shares.assign(split=shares["share"] / inside).sort_values("split", ascending=False)
    top = norm.iloc[0]
    if top["split"] >= NEST_TOLERANCE:
        if top["split"] < 1 - 1e-9:
            s.log.append(
                (name, "nested_within_tolerance", f"{top['split']:.2%} in {top['feature_id']}")
            )
        s.exact += 1
        exact_basis = "jurisdiction" if geography == "municipality" else basis
        s.rows.append(_row(name, top, 1.0, "exact", exact_basis))
        return
    slivers = norm[norm["split"] < MIN_SHARE]
    if not slivers.empty:
        s.log.append((name, "sliver_dropped", f"{len(slivers)} pieces < {MIN_SHARE:.1%}"))
    kept = norm[norm["split"] >= MIN_SHARE]
    total = float(kept["split"].sum())
    s.allocated += 1
    for _, piece in kept.iterrows():
        s.rows.append(_row(name, piece, float(piece["split"]) / total, "allocated", basis))


def _row(name: str, piece: pd.Series, split: float, method: str, basis: str) -> dict[str, object]:
    return {
        "precinct_name": name,
        "feature_id": piece["feature_id"],
        "pop_share": None if pd.isna(piece["pop_share"]) else float(piece["pop_share"]),
        "area_share": float(piece["area_share"]),
        "split_share": split,
        "method": method,
        "weight_basis": basis,
    }


def _pieces(
    precincts: gpd.GeoDataFrame, targets: gpd.GeoDataFrame, blocks: gpd.GeoDataFrame
) -> tuple[gpd.GeoDataFrame, pd.Series]:
    """Precinct x unit pieces with area and population shares; plus precinct population."""
    pieces = gpd.overlay(
        precincts[["precinct_name", "geometry"]],
        targets[["feature_id", "geometry"]],
        how="intersection",
        keep_geom_type=True,
    )
    p_pop = _population(blocks, precincts, ["precinct_name"])
    piece_pop = _population(blocks, pieces, ["precinct_name", "feature_id"])
    p_area = precincts.set_index("precinct_name").area
    pieces["area_share"] = pieces.area / pieces["precinct_name"].map(p_area)
    pieces["pop_share"] = [
        piece_pop.get((n, f), 0.0) / p_pop[n] if p_pop.get(n, 0) > 0 else float("nan")
        for n, f in zip(pieces["precinct_name"], pieces["feature_id"], strict=True)
    ]
    return pieces, p_pop


def compute_crosswalk(
    con: duckdb.DuckDBPyConnection,
    precinct_set_id: str,
    target_set_id: str,
    geography: str,
    county: str,
    blocks_vintage: int,
) -> CrosswalkSummary:
    s = CrosswalkSummary(precinct_set_id, target_set_id)
    precincts = (
        read_features(con, precinct_set_id)
        .to_crs(AREA_CRS)
        .rename(columns={"feature_id": "precinct_name"})
    )
    targets = read_features(con, target_set_id).to_crs(AREA_CRS)
    precincts = _eligible(precincts, targets, geography, s)
    s.eligible = len(precincts)
    blocks = read_blocks(con, county, blocks_vintage).to_crs(AREA_CRS)
    pieces, p_pop = _pieces(precincts, targets, blocks)
    for name in precincts["precinct_name"]:
        mine = pieces[pieces["precinct_name"] == name]
        if mine.empty:
            s.no_overlap += 1
            s.log.append(
                (name, "no_overlap", "eligible precinct touches no unit; votes unassigned")
            )
            continue
        if p_pop.get(name, 0) > 0 and mine["pop_share"].sum() > 0:
            _decide(name, mine.assign(share=mine["pop_share"]), "population", geography, s)
        else:
            why = (
                "no 2020 block population"
                if p_pop.get(name, 0) <= 0
                else "no population in any unit"
            )
            s.log.append((name, "zero_population", f"{why}; area weights used"))
            _decide(name, mine.assign(share=mine["area_share"]), "area", geography, s)
    return s
