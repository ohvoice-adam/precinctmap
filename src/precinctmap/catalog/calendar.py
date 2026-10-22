"""Known Franklin County election dates. Used to resolve an election from (year, type).

Add a row here, with its source, before ingesting an election that is not listed. Dates are
the statutory Ohio election days; 2024's primary was moved to March for the presidential race.
"""

from datetime import date
from typing import Literal

ElectionType = Literal["primary", "general", "special"]

FRANKLIN_ELECTIONS: dict[date, ElectionType] = {
    date(2016, 3, 15): "primary",
    date(2016, 11, 8): "general",
    date(2020, 4, 28): "primary",  # moved from March 17 (COVID-19); mostly by mail
    date(2020, 11, 3): "general",
    date(2022, 5, 3): "primary",
    date(2022, 8, 2): "primary",  # second primary (state legislature, after redistricting)
    date(2022, 11, 8): "general",
    date(2023, 5, 2): "primary",
    date(2023, 8, 8): "special",  # statewide Issue 1
    date(2023, 11, 7): "general",
    date(2024, 3, 19): "primary",
    date(2024, 11, 5): "general",
    date(2025, 5, 6): "primary",
    date(2025, 11, 4): "general",
    date(2026, 5, 5): "primary",
    date(2026, 11, 3): "general",
}


def find(year: int, election_type: ElectionType) -> list[date]:
    """Calendar dates in `year` of `election_type` (usually zero or one)."""
    return sorted(d for d, t in FRANKLIN_ELECTIONS.items() if d.year == year and t == election_type)
