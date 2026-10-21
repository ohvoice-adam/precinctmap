"""ACS tables read and the measures built from them.

Line numbers are the summary file's estimate columns (`B15003_E022` is line 22), checked
against the ACS 2020-2024 5-year table shells. A measure is numerator lines over denominator
lines from one table; `weight` says how a block group's estimate is split across its blocks
(2020 block population for people, 2020 housing units for households).

Measures were chosen as the demographic characteristics most consistently associated with
area-level vote patterns in recent elections (see project-docs/census.md); the app labels
them neutrally and never as political indicators.
"""

from dataclasses import dataclass
from typing import Literal

Weight = Literal["pop", "housing"]
Kind = Literal["count", "share", "currency", "density"]


@dataclass(frozen=True)
class Measure:
    metric: str
    label: str
    group: str
    kind: Kind
    table: str
    num: tuple[int, ...]  # for 'median': the income bracket lines, lowest first
    den: tuple[int, ...]  # empty for counts, medians and density
    weight: Weight
    universe: str  # what `base` counts, e.g. "adults 25 and older"
    description: str


def _r(a: int, b: int) -> tuple[int, ...]:
    return tuple(range(a, b + 1))


# B19001 brackets (lines 2-17): lower edge of each; the last is open-ended ($200,000 or more).
INCOME_EDGES: tuple[int, ...] = (
    0, 10_000, 15_000, 20_000, 25_000, 30_000, 35_000, 40_000, 45_000,
    50_000, 60_000, 75_000, 100_000, 125_000, 150_000, 200_000,
)  # fmt: skip
INCOME_TOP = 200_000

G_EDU, G_AGE, G_RACE, G_IMM = "Education", "Age and household", "Race and ethnicity", "Immigration"
G_HOUSE, G_URBAN, G_PEOPLE = "Housing and income", "Urbanism", "Population"


def _share(
    metric: str, label: str, group: str, table: str, num: tuple[int, ...], den: tuple[int, ...],
    universe: str, description: str, weight: Weight = "pop",
) -> Measure:  # fmt: skip
    return Measure(metric, label, group, "share", table, num, den, weight, universe, description)


MEASURES: tuple[Measure, ...] = (
    Measure("population", "Population", G_PEOPLE, "count", "B01003", (1,), (), "pop",
            "people", "Total population (B01003)."),
    Measure("households", "Households", G_PEOPLE, "count", "B25003", (1,), (), "housing",
            "households", "Occupied housing units (B25003)."),
    _share("bachelors_share", "Bachelor's degree or higher", G_EDU, "B15003", _r(22, 25), (1,),
           "adults 25 and older", "Share of adults 25+ with a bachelor's, master's, professional"
           " or doctoral degree (B15003)."),
    _share("graduate_share", "Graduate or professional degree", G_EDU, "B15003", _r(23, 25), (1,),
           "adults 25 and older", "Share of adults 25+ with a master's, professional or doctoral"
           " degree (B15003)."),
    _share("young_adult_share", "Adults 18 to 34", G_AGE, "B01001", _r(7, 12) + _r(31, 36),
           _r(7, 25) + _r(31, 49), "adults 18 and older", "Share of adults who are 18 to 34"
           " (B01001)."),
    _share("never_married_share", "Never married", G_AGE, "B12001", (3, 12), (1,),
           "people 15 and older", "Share of people 15+ who have never married (B12001)."),
    _share("white_nh_share", "White, not Hispanic", G_RACE, "B03002", (3,), (1,), "people",
           "White alone, not Hispanic or Latino (B03002)."),
    _share("black_share", "Black, not Hispanic", G_RACE, "B03002", (4,), (1,), "people",
           "Black or African American alone, not Hispanic or Latino (B03002)."),
    _share("hispanic_share", "Hispanic or Latino", G_RACE, "B03002", (12,), (1,), "people",
           "Hispanic or Latino, of any race (B03002)."),
    _share("asian_share", "Asian, not Hispanic", G_RACE, "B03002", (6,), (1,), "people",
           "Asian alone, not Hispanic or Latino (B03002)."),
    _share("foreign_born_share", "Born outside the U.S.", G_IMM, "B05002", (13,), (1,), "people",
           "Foreign-born residents, naturalized or not (B05002)."),
    _share("noncitizen_share", "Not a U.S. citizen", G_IMM, "B05002", (21,), (1,), "people",
           "Foreign-born residents who are not U.S. citizens (B05002). The ACS does not ask"
           " about legal or immigration status."),
    _share("renter_share", "Renter households", G_HOUSE, "B25003", (3,), (1,), "households",
           "Share of occupied housing units that are renter-occupied (B25003).", "housing"),
    _share("rent_burdened_share", "Renters paying 30% or more of income on rent", G_HOUSE,
           "B25070", _r(7, 10), _r(2, 10), "renter households (rent burden computed)",
           "Gross rent 30% or more of household income; excludes renters for whom it can't be"
           " computed (B25070).", "housing"),
    Measure("median_household_income", "Median household income", G_HOUSE, "currency", "B19001",
            _r(2, 17), (), "housing", "households", "Estimated from household income brackets"
            " (B19001) by linear interpolation; $200,000+ is the top bracket."),
    _share("low_income_share", "Below 200% of the poverty line", G_HOUSE, "C17002", _r(2, 7), (1,),
           "people (poverty status determined)", "Income below twice the federal poverty"
           " threshold (C17002)."),
    _share("transit_walk_bike_share", "Commute by transit, walking or bike", G_URBAN, "B08301",
           (10, 18, 19), (1,), "workers 16 and older", "Public transportation, bicycle or walking"
           " as the usual way to work (B08301)."),
    _share("work_from_home_share", "Work from home", G_URBAN, "B08301", (21,), (1,),
           "workers 16 and older", "Workers who usually worked from home (B08301)."),
    Measure("population_density", "People per square mile", G_URBAN, "density", "B01003", (1,),
            (), "pop", "people", "Population (B01003) per square mile of 2020 block land area."),
)  # fmt: skip
BY_ID = {m.metric: m for m in MEASURES}
TABLES: tuple[str, ...] = tuple(sorted({m.table for m in MEASURES}))
WEIGHTS: dict[str, Weight] = {m.table: m.weight for m in MEASURES}
# Tables the summary file publishes only down to tracts; everything else uses block groups.
TRACT_ONLY: frozenset[str] = frozenset({"B05002"})
UNIT_DIGITS = {"block_group": 12, "tract": 11}


def level_of(table: str) -> str:
    return "tract" if table in TRACT_ONLY else "block_group"
