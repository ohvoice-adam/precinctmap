"""Known Franklin County election dates. Used to resolve an election from (year, type).

Add a row here, with its source, before ingesting an election that is not listed. Dates are
the statutory Ohio election days; 2024's primary was moved to March for the presidential race.
"""

from datetime import date
from typing import Literal

ElectionType = Literal["primary", "general", "special"]

FRANKLIN_ELECTIONS: dict[date, ElectionType] = {
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
