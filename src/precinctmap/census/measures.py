"""Every census measure for every feature of every geography (rows for census_stats)."""

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from precinctmap.census.allocate import unit_weights
from precinctmap.census.blocks import BlockAssignment
from precinctmap.census.estimates import (
    line_sum,
    median_from_brackets,
    proportion,
    reliable,
    to_features,
)
from precinctmap.census.summary_file import TableData
from precinctmap.census.tables import INCOME_EDGES, INCOME_TOP, MEASURES, Measure, level_of

RECONCILE_TOLERANCE = 1e-6  # relative


class CensusTotalsError(AssertionError):
    pass


@dataclass
class Computed:
    stats: (
        pd.DataFrame
    )  # geography, boundary_set_id, feature_id, metric, value, moe, base, reliable
    log: list[tuple[str, str]] = field(default_factory=list)


def _values(m: Measure, t: TableData, w: pd.DataFrame, land: pd.Series) -> pd.DataFrame:
    if m.kind == "currency":
        return _median(m, t, w)
    num = to_features(line_sum(t.estimates, t.moes, m.num), w)
    if m.kind == "share":
        return proportion(num, to_features(line_sum(t.estimates, t.moes, m.den), w))
    moe = np.sqrt(num["V"])
    if m.kind == "density":
        area = land.reindex(num.index)
        area = area.where(area > 0)
        return pd.DataFrame({"value": num["E"] / area, "moe": moe / area, "base": num["E"]})
    return pd.DataFrame({"value": num["E"], "moe": moe, "base": num["E"]})


def _median(m: Measure, t: TableData, w: pd.DataFrame) -> pd.DataFrame:
    brackets = {k: to_features(line_sum(t.estimates, t.moes, (k,)), w) for k in m.num}
    e = pd.concat({k: b["E"] for k, b in brackets.items()}, axis=1).fillna(0.0)
    v = pd.concat({k: b["V"] for k, b in brackets.items()}, axis=1).fillna(0.0)
    rows = {
        fid: median_from_brackets(
            e.loc[fid].to_numpy(), v.loc[fid].to_numpy(), INCOME_EDGES, INCOME_TOP
        )
        for fid in e.index
    }
    out = pd.DataFrame.from_dict(rows, orient="index", columns=["value", "moe"])
    out["base"] = e.sum(axis=1)
    return out


def _check_total(geo: str, m: Measure, t: TableData, w: pd.DataFrame, got: float) -> None:
    """Mapped total = the units' estimates times the share of each unit that was placed."""
    units = line_sum(t.estimates, t.moes, m.num)["E"]
    placed = w.groupby("unit")["w"].sum()
    want = float((units.reindex(placed.index).fillna(0) * placed).sum())
    if abs(got - want) > RECONCILE_TOLERANCE * max(want, 1.0):
        raise CensusTotalsError(f"{geo} {m.metric}: {got:,.1f} mapped, {want:,.1f} expected")


def compute(tables: dict[str, TableData], assigned: BlockAssignment) -> Computed:
    blocks = assigned.blocks
    out = Computed(pd.DataFrame())
    frames = []
    for geo, set_id in assigned.set_ids.items():
        land = blocks.groupby(geo)["land_sqmi"].sum()
        weights = {}
        for m in MEASURES:
            key = (level_of(m.table), m.weight)
            if key not in weights:
                weights[key] = unit_weights(blocks, geo, *key)
                out.log.extend((f"{geo}_{i}", d) for i, d in weights[key].fallbacks)
            w = weights[key].frame
            vals = _values(m, tables[m.table], w, land)
            if m.kind == "count":
                _check_total(geo, m, tables[m.table], w, float(vals["value"].sum()))
            vals = vals.rename_axis("feature_id").reset_index()
            vals["reliable"] = [
                reliable(v, e) for v, e in zip(vals["value"], vals["moe"], strict=True)
            ]
            frames.append(vals.assign(geography=geo, boundary_set_id=set_id, metric=m.metric))
    stats = pd.concat(frames, ignore_index=True)
    out.stats = stats.astype({"value": float, "moe": float, "base": float})
    return out


def unplaced_units(tables: dict[str, TableData], blocks: pd.DataFrame) -> list[tuple[str, str]]:
    """ACS units with estimates but no 2020 blocks (their people would go unmapped)."""
    log = []
    for table, t in tables.items():
        level = level_of(table)
        missing = sorted(set(t.estimates.index) - set(blocks[level]))
        people = float(t.estimates.loc[missing, 1].sum()) if missing else 0.0
        if missing:
            log.append(
                (
                    f"{table}_units_without_blocks",
                    f"{len(missing)} {level}s, {people:,.0f} in line 1",
                )
            )
    return log
