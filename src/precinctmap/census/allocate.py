"""Shares of each ACS unit (block group or tract) that fall in each feature.

w(feature, unit) = the unit's 2020 block population (or housing units) whose blocks count in
the feature, over the unit's total. A unit whose blocks have no population (or housing) falls
back to block land area, then to an equal share per block, and is logged. Units missing from
the block file are reported, never silently dropped.
"""

from dataclasses import dataclass, field

import pandas as pd

from precinctmap.census.tables import Weight


@dataclass
class Weights:
    frame: pd.DataFrame  # columns feature_id, unit, w
    fallbacks: list[tuple[str, str]] = field(default_factory=list)


def _basis(blocks: pd.DataFrame, level: str, weight: Weight) -> tuple[pd.Series, list[str]]:
    """Per-block weight on `weight`, with fallbacks where a unit's total is zero."""
    basis = blocks[weight].astype(float)
    unit = blocks[level]
    totals = basis.groupby(unit).transform("sum")
    land = blocks["land_sqmi"].astype(float)
    land_totals = land.groupby(unit).transform("sum")
    use_land = (totals <= 0) & (land_totals > 0)
    equal = (totals <= 0) & (land_totals <= 0)
    basis = basis.where(~use_land, land).where(~equal, 1.0)
    fell_back = sorted(set(unit[use_land | equal]))
    return basis, fell_back


def unit_weights(blocks: pd.DataFrame, geography: str, level: str, weight: Weight) -> Weights:
    """Feature x unit shares for one geography; blocks without a feature are left out."""
    basis, fell_back = _basis(blocks, level, weight)
    unit_total = basis.groupby(blocks[level]).sum()
    frame = pd.DataFrame({"feature_id": blocks[geography], "unit": blocks[level], "b": basis})
    frame = frame.dropna(subset=["feature_id"])
    grouped = pd.DataFrame(frame.groupby(["feature_id", "unit"], as_index=False)["b"].sum())
    grouped["w"] = grouped["b"] / grouped["unit"].map(unit_total)
    out = Weights(grouped[["feature_id", "unit", "w"]])
    if fell_back:
        out.fallbacks.append(
            (f"{level}_{weight}_fallback", f"{len(fell_back)} {level}s with no {weight}; by area")
        )
    return out
