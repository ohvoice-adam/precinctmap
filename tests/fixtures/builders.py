"""Tiny synthetic FCBOE-style workbooks, built in code and written to tmp .xlsx files.

Shapes mirror the real samples (3 header rows, precinct rows, pseudo-rows, ZZZ total row)
with a handful of precincts. The ZZZ row is computed from the rows unless overridden.
"""

from dataclasses import dataclass, field
from pathlib import Path

import geopandas as gpd
import openpyxl
from shapely.geometry import box

Cell = int | str


@dataclass
class Col:
    h1: str
    h2: str
    h3: str
    values: list[Cell]  # one per data row (precincts and pseudo-rows), ZZZ excluded


@dataclass
class Sheet:
    rows: list[tuple[str, str]]  # (code, name)
    cols: list[Col]
    county_number: int = 25
    total_overrides: dict[int, Cell] = field(default_factory=dict)  # col index -> ZZZ value

    def grid(self) -> list[list[object]]:
        ids = [("COUNTY NUMBER", "", ""), ("PRECINCT CODE", "", ""), ("PRECINCT NAME", "", "")]
        header = [
            [h[i] for h in ids] + [getattr(c, f"h{i + 1}") for c in self.cols] for i in range(3)
        ]
        body: list[list[object]] = [
            [self.county_number, code, name, *[c.values[r] for c in self.cols]]
            for r, (code, name) in enumerate(self.rows)
        ]
        totals: list[object] = [self.county_number, "ZZZ", "COUNTY TOTALS"]
        for i, c in enumerate(self.cols):
            totals.append(self.total_overrides.get(i, sum(v for v in c.values if v != "")))
        return [*header, *body, totals]

    def write(self, path: Path) -> Path:
        wb = openpyxl.Workbook()
        ws = wb.active
        assert ws is not None
        for row in self.grid():
            ws.append(row)
        wb.save(path)
        return path


def sheet_2025(*, zoo_extra: int = 0) -> Sheet:
    """2025-layout general: Bexley council (on one precinct's ballot) and a countywide levy.

    `zoo_extra` adds votes to the levy's 'For' column in the first precinct (a "corrected" file).
    Every precinct satisfies cands + under + 1*over == ballots, so vote-for infers as 1.
    """
    rows = [
        ("0001", "COLUMBUS 01-A"),
        ("0002", "BEXLEY 1-A"),
        ("0003", "BLENDON-A"),
        ("0004", "Delaware County"),
    ]
    council = "For Member of Council City of Bexley"
    zoo = "#1 Proposed Tax Levy - Zoo"
    return Sheet(
        rows,
        [
            Col("REGISTERED VOTERS TOTAL", "", "VOTERS", [100, 200, 150, 0]),
            Col("BALLOTS CAST TOTAL", "", "BALLOTS CAST", [50 + zoo_extra, 80, 60, 0]),
            Col("BALLOTS CAST BLANK", "", "BALLOTS CAST", [0, 0, 1, 0]),
            Col(council, "Non", "Rep Ann Lee", [0, 40, 0, 0]),
            Col(council, "Non", "Dem GeraldÂ\xa0Dixon", [0, 30, 0, 0]),
            Col(council, "Non", "OVER VOTES", [0, 2, 0, 0]),
            Col(council, "Non", "UNDER VOTES", [0, 8, 0, 0]),
            Col(zoo, "Non", "For the Tax Levy", [30 + zoo_extra, 50, 35, 10]),
            Col(zoo, "Non", "Against the Tax Levy", [15, 25, 20, 5]),
            Col(zoo, "Non", "OVER VOTES", [1, 0, 1, 0]),
            Col(zoo, "Non", "UNDER VOTES", [4, 5, 4, 1]),
        ],
    )


def sheet_2025_primary() -> Sheet:
    """2025-layout primary: a Dem party-ballot contest and party turnout columns."""
    rows = [("0001", "COLUMBUS 01-A"), ("0002", "BEXLEY 1-A"), ("0003", "Union County")]
    mayor = "Dem For Mayor - City of Bexley"
    return Sheet(
        rows,
        [
            Col("REGISTERED VOTERS TOTAL", "", "VOTERS", [100, 200, 0]),
            Col("REGISTERED VOTERS - Democratic", "Dem", "VOTERS", [40, 90, 0]),
            Col("BALLOTS CAST TOTAL", "", "BALLOTS CAST", [20, 30, 0]),
            Col("BALLOTS CAST - Democratic", "Dem", "BALLOTS CAST", [20, 30, 0]),
            Col("BALLOTS CAST BLANK", "", "BALLOTS CAST", [0, 0, 0]),
            Col(mayor, "Dem", "Pat Kim", [12, 20, 3]),
            Col(mayor, "Dem", "OVER VOTES", [0, 0, 0]),
            Col(mayor, "Dem", "UNDER VOTES", [8, 10, 1]),
        ],
    )


def sheet_2024(*, primary: bool = False) -> Sheet:
    """2024-layout file: blank cells mean 'not on this ballot'; bare-name pseudo-row."""
    rows = [("AAA", "COLUMBUS 01-A"), ("AAB", "BEXLEY 1-A"), ("AAC", "BLENDON-A"), ("", "Clark")]
    cols = [
        Col("REGISTERED VOTERS", "", "", [100, 200, 150, 0]),
        Col("TOTAL VOTERS", "", "", [50, 80, 60, 0]),
    ]
    if primary:
        cols.append(Col("Democratic", "Dem", "", [50, 80, 60, 0]))
        senate = "Dem For U.S. Senator -"
        cols += [Col(senate, "Dem", "Sherrod Brown", [45, 70, 50, 7])]
    else:
        pres = "For President and Vice President -"
        cols += [
            Col(pres, "Dem", "Dem Ann Lee", [30, 50, 35, 9]),
            Col(pres, "Rep", "Rep Bob Roe", [18, 28, 22, 4]),
        ]
    rep = "For State Representative (1st District)"
    cols += [
        Col(rep, "Dem" if primary else "Non", "Cy Doe", [40, "", 0, ""]),
        Col(rep, "Dem" if primary else "Non", "Write-in", [1, "", 0, ""]),
    ]
    if primary:
        cols[-2].h1 = cols[-1].h1 = "Dem " + rep
    return Sheet(rows, cols)


def precinct_shapefile(path: Path, names: list[str]) -> Path:
    """Unit squares (EPSG:3735 feet) named like BOE precincts, side by side."""
    gdf = gpd.GeoDataFrame(
        {"NAME": names},
        geometry=[
            box(1_800_000 + i * 1000, 700_000, 1_800_900 + i * 1000, 700_900)
            for i in range(len(names))
        ],
        crs=3735,
    )
    gdf.to_file(path)
    return path


# --- Mini-county results (precinct names match tests/fixtures/geo.py) ---------------

NAMES = ["COLUMBUS 01-A", "COLUMBUS 01-B", "BLENDON-A", "HAMILTON-A", "OBETZ-D"]
LEVY_FOR = [100, 50, 40, 10, 20]  # countywide issue
COUNCIL_VOTES = [30, 20, 0, 0, 0]  # Columbus-only contest (absent elsewhere)


def mini_county_sheet() -> Sheet:
    """2025-layout general for the mini-county in tests/fixtures/geo.py."""
    rows = [(f"{i + 1:04d}", n) for i, n in enumerate(NAMES)]
    levy, council = "#1 Proposed Tax Levy - Zoo", "For Member of Council City of Columbus"
    ballots = [v + 5 for v in LEVY_FOR]
    return Sheet(
        rows,
        [
            Col("REGISTERED VOTERS TOTAL", "", "VOTERS", [200, 100, 80, 20, 40]),
            Col("BALLOTS CAST TOTAL", "", "BALLOTS CAST", ballots),
            Col(levy, "Non", "For the Tax Levy", LEVY_FOR),
            Col(levy, "Non", "Against the Tax Levy", [5, 5, 5, 5, 5]),
            Col(levy, "Non", "OVER VOTES", [0] * 5),
            Col(levy, "Non", "UNDER VOTES", [0] * 5),
            Col(council, "Non", "Ann Lee", COUNCIL_VOTES),
            Col(council, "Non", "OVER VOTES", [0] * 5),
            Col(council, "Non", "UNDER VOTES", [1, 1, 0, 0, 0]),
        ],
    )
