"""Synthetic national ACS summary files for the mini-county (tests/fixtures/geo.py).

Each table file carries a US row, another county's block group (which fetching must drop),
the mini-county's three block groups and two tracts, and its county row. Lines not listed are
0 with MOE 0.
"""

from pathlib import Path

from precinctmap.census.summary_file import file_name

YEAR = 2024
BG_A, BG_B, BG_C = "390490001001", "390490001002", "390490002001"  # x 0-2000, 2000-3000, 3000-5000
TRACT_1, TRACT_2 = "39049000100", "39049000200"  # A + B, C
LINES = {"B01001": 49, "B01003": 1, "B03002": 21, "B05002": 27, "B05003": 23,
         "B08301": 21, "B12001": 19,
         "B15003": 25, "B19001": 17, "B25003": 3, "B25070": 11, "C17002": 8}  # fmt: skip

# table -> unit -> {line: (estimate, moe)}
DATA: dict[str, dict[str, dict[int, tuple[int, int]]]] = {
    "B01003": {BG_A: {1: (200, 20)}, BG_B: {1: (100, 30)}, BG_C: {1: (100, 10)}},
    "B15003": {
        BG_A: {1: (120, 12), 22: (40, 10), 23: (10, 5), 24: (5, 4), 25: (5, 4)},  # 60/120
        BG_B: {1: (60, 9), 22: (6, 5)},  # 6/60
        BG_C: {1: (70, 8), 22: (14, 6), 23: (7, 5)},  # 21/70
    },
    "B19001": {  # households by bracket (line 2 = under $10k ... 17 = $200k+)
        BG_A: {1: (80, 8), 11: (20, 6), 12: (40, 9), 13: (20, 6)},  # median inside $60-75k
        BG_B: {1: (40, 6), 2: (40, 6)},
        BG_C: {1: (40, 6), 17: (40, 6)},  # all in the open top bracket
    },
    "B25003": {
        BG_A: {1: (80, 8), 2: (20, 5), 3: (60, 8)},
        BG_B: {1: (40, 6), 2: (40, 6)},
        BG_C: {1: (40, 6), 2: (10, 4), 3: (30, 6)},
    },
    "B05002": {
        TRACT_1: {1: (300, 30), 13: (60, 15), 14: (30, 12), 21: (30, 12)},
        TRACT_2: {1: (100, 10), 13: (5, 4), 14: (5, 4), 21: (0, 9)},
    },
    "B05003": {  # 9/20 native and 11/22 naturalized adults (male/female)
        TRACT_1: {1: (300, 30), 9: (150, 15), 11: (20, 8), 20: (100, 12), 22: (10, 6)},  # 30/280
        TRACT_2: {1: (100, 10), 9: (40, 8), 11: (0, 4), 20: (40, 8), 22: (0, 4)},
    },
}


def _row(geo_id: str, table: str, values: dict[int, tuple[int, int]]) -> str:
    cells = [geo_id]
    for line in range(1, LINES[table] + 1):
        e, m = values.get(line, (0, 0))
        cells += [str(e), str(m)]
    return "|".join(cells)


def _county(table: str) -> dict[int, tuple[int, int]]:
    """County row: the sum of the mini-county's units of the table's level (MOE controlled)."""
    out: dict[int, tuple[int, int]] = {}
    for values in DATA.get(table, {}).values():
        for line, (e, _) in values.items():
            out[line] = (out.get(line, (0, 0))[0] + e, -555555555)
    return out


def write_national_tables(root: Path, year: int = YEAR) -> Path:
    """Write every table under root/<year>/table-based-SF/data/5YRData/; returns `root`."""
    out = root / str(year) / "table-based-SF" / "data" / "5YRData"
    out.mkdir(parents=True, exist_ok=True)
    for table, n in LINES.items():
        header = "GEO_ID|" + "|".join(f"{table}_{k}{i:03d}" for i in range(1, n + 1) for k in "EM")
        units = DATA.get(table, {})
        level = "1400000US" if table in ("B05002", "B05003") else "1500000US"
        rows = [header, _row("0100000US", table, {1: (9_999, 0)})]
        rows.append(_row("1500000US390410001001", table, {1: (777, 50)}))  # Delaware County
        rows += [_row(f"{level}{u}", table, v) for u, v in units.items()]
        if not units:  # tables the tests don't exercise still need the county's units
            rows += [
                _row(f"{level}{u}", table, {})
                for u in ((TRACT_1, TRACT_2) if level == "1400000US" else (BG_A, BG_B, BG_C))
            ]
        rows.append(_row("0500000US39049", table, _county(table)))
        (out / file_name(year, table)).write_text("\n".join(rows) + "\n", encoding="utf-8")
    return root
