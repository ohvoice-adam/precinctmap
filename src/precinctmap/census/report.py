"""Plain-text review report for an ACS release (printed before anything is committed)."""

from precinctmap.census.load import CensusReview
from precinctmap.census.tables import BY_ID

SHOWN = ("population", "bachelors_share", "median_household_income", "noncitizen_share")


def _fmt(metric: str, value: float) -> str:
    kind = BY_ID[metric].kind
    if kind == "share":
        return f"{value:.1%}"
    if kind == "currency":
        return f"${value:,.0f}"
    return f"{value:,.0f}"


def render(r: CensusReview) -> str:
    lines = [f"Census review {r.release_id}: {r.label}, boundaries as of {r.as_of}", ""]
    lines.append("Tables (county rows only; sum of units vs the published county row):")
    for f, (table, units, county) in zip(r.files, r.county_checks, strict=True):
        unit = f"{f.block_groups} block groups" if f.block_groups else f"{f.tracts} tracts"
        ok = "ok" if abs(units - county) <= 0.5 else "DIFFERS"
        lines.append(
            f"  {table}: {unit}, {units:,.0f} vs {county:,.0f} {ok}  sha256 {f.sha256[:12]}"
        )
    lines.append("")
    lines.append(
        f"Blocks: {r.blocks:,}; placed per geography: "
        + ", ".join(f"{g} {n:,}" for g, n in r.placed.items())
    )
    stats = r.computed.stats
    lines.append("")
    lines.append("Areas and reliability (CV <= 30%):")
    for geo in r.placed:
        sub = stats[stats["geography"] == geo]
        parts = []
        for metric in SHOWN:
            m = sub[sub["metric"] == metric]
            parts.append(f"{metric} {m['reliable'].mean():.0%} reliable")
        lines.append(f"  {geo}: {sub['feature_id'].nunique():,} areas; " + "; ".join(parts))
    pop = stats[(stats["geography"] == "precinct") & (stats["metric"] == "population")]
    lines.append(f"\nPopulation mapped to precincts: {pop['value'].sum():,.0f}")
    lines.append("")
    lines.append(f"Log entries ({len(r.log)}):")
    lines.extend(f"  {issue}: {detail}" for issue, detail in r.log)
    return "\n".join(lines)
