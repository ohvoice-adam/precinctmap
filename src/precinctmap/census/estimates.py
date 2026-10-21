"""Derived ACS estimates and their 90% margins of error.

Follows the Census Bureau's guidance for derived estimates ("Understanding and Using ACS
Data", chapter 8): sums add estimates and take the root of summed squared MOEs, counting the
MOE of zero estimates only once (the largest) within a unit; proportions use the proportion
formula, falling back to the ratio formula when the radicand is negative. Allocated parts of a
unit scale its estimate and MOE by the share w (an approximation, since a unit's blocks are not
sampled separately). The median income MOE replaces the published design factor with the
standard error of the cumulative share at the median bracket, computed from bracket MOEs.
"""

import math

import numpy as np
import pandas as pd

Z90 = 1.645
MAX_CV = 0.30  # coefficient of variation above which an estimate is flagged as unreliable


def line_sum(est: pd.DataFrame, moe: pd.DataFrame, lines: tuple[int, ...]) -> pd.DataFrame:
    """Per unit: E (sum of lines) and V (summed squared MOE, zero estimates counted once)."""
    e = est[list(lines)]
    m2 = moe[list(lines)] ** 2
    zero = e == 0
    v = m2.where(~zero, 0.0).sum(axis=1) + m2.where(zero, 0.0).max(axis=1)
    return pd.DataFrame({"E": e.sum(axis=1), "V": v})


def to_features(units: pd.DataFrame, weights: pd.DataFrame) -> pd.DataFrame:
    """Feature totals: E = sum(w E), V = sum(w^2 V) over the units each feature draws on."""
    j = weights.join(units, on="unit", how="inner")
    j["E"] *= j["w"]
    j["V"] *= j["w"] ** 2
    return j.groupby("feature_id")[["E", "V"]].sum()


def proportion(num: pd.DataFrame, den: pd.DataFrame) -> pd.DataFrame:
    """value = N/D and its MOE; NaN where the denominator is 0."""
    d = den["E"].reindex(num.index)
    dv = den["V"].reindex(num.index)
    p = num["E"] / d.where(d > 0)
    radicand = num["V"] - p**2 * dv
    ratio = num["V"] + p**2 * dv
    moe = np.sqrt(radicand.where(radicand >= 0, ratio)) / d.where(d > 0)
    return pd.DataFrame({"value": p, "moe": moe, "base": d})


def reliable(value: float | None, moe: float | None) -> bool:
    """CV <= MAX_CV; a zero or missing estimate with any sampling error is not reliable."""
    if value is None or moe is None or math.isnan(value) or math.isnan(moe):
        return False
    if value == 0:
        return moe == 0
    return (moe / Z90) / abs(value) <= MAX_CV


def _interpolate(
    cum: np.ndarray, counts: np.ndarray, edges: tuple[int, ...], top: int, p: float
) -> float:
    """Income at cumulative share `p` (0-1), linear within the bracket; capped at `top`."""
    target = p * cum[-1]
    k = int(np.searchsorted(cum, target, side="left"))
    if k >= len(edges) - 1:
        return float(top)
    below = cum[k - 1] if k > 0 else 0.0
    frac = (target - below) / counts[k] if counts[k] > 0 else 0.0
    return edges[k] + frac * (edges[k + 1] - edges[k])


def median_from_brackets(
    e: np.ndarray, v: np.ndarray, edges: tuple[int, ...], top: int
) -> tuple[float | None, float | None]:
    """Median and MOE from bracket counts `e` and squared MOEs `v` (lowest bracket first)."""
    total = float(e.sum())
    if total <= 0:
        return None, None
    cum = np.cumsum(e)
    median = _interpolate(cum, e, edges, top, 0.5)
    k = int(np.searchsorted(cum, 0.5 * total, side="left"))
    below = max(k - 1, 0)
    c, cv = float(cum[below]), float(v[: below + 1].sum())
    p = c / total
    radicand = cv - p**2 * float(v.sum())
    moe_p = math.sqrt(radicand if radicand >= 0 else cv + p**2 * float(v.sum())) / total
    lo = _interpolate(cum, e, edges, top, max(0.5 - moe_p, 0.0))
    hi = _interpolate(cum, e, edges, top, min(0.5 + moe_p, 1.0))
    return median, (hi - lo) / 2
