"""A tiny synthetic FCBOE 2016 multi-sheet workbook; see fcboe_sheets_2016.

Splits: COLUMBUS 01-A (one split), COLUMBUS 01-B (two splits, 01001B-1/-2) and BLENDON-A.
Sheets: Democratic (Senate with 2 choices, a one-choice Congress race), Republican (Senate),
Green (one write-in race, two extra ID columns like the real file), Questions & Issues (levy).
"""

from dataclasses import dataclass, field
from pathlib import Path

import openpyxl

IDS = ["DISTRICT NUMBER", "WARD NUMBER", "PRECINCT CODE", "PRECINCT CODE WITH SPLIT", "LID",
       "CITY OR VILLAGE", "TOWNSHIP", "CONGRESS DISTRICT", "SENATE DISTRICT", "HOUSE DISTRICT",
       "POLICE DISTRICT", "FIRE DISTRICT", ""]  # fmt: skip
SPLITS = [  # code, split, name, registered, voters, dem, rep, green
    ("01001A", "01001A-1", "COLUMBUS 01-A 01", 100, 50, 30, 19, 1),
    ("01001B", "01001B-1", "COLUMBUS 01-B 01", 80, 40, 20, 20, 0),
    ("01001B", "01001B-2", "COLUMBUS 01-B 02", 10, 4, 3, 1, 0),
    ("03000A", "03000A-1", "BLENDON-A 01", 60, 30, 10, 20, 0),
]
TURNOUT = ["REGISTERED VOTERS", "TOTAL VOTERS", "DEMOCRATIC", "REPUBLICAN", "GREEN"]


@dataclass
class Race:
    name: str
    code: str  # DEM / REP / GRE / ''
    labels: list[str]
    votes: list[list[int]]  # per split row, per choice


SHEETS: dict[str, list[Race]] = {
    "Democratic": [
        Race("United States Senator", "DEM", ["Ted Strickland", "P.G. Sittenfeld"],
             [[15, 10], [10, 8], [2, 1], [5, 4]]),
        Race("Chief Justice of the Supreme Court", "DEM", ["NO CANDIDATE FILED"],
             [[0], [0], [0], [0]]),
    ],
    "Republican": [Race("United States Senator", "REP", ["Rob Portman"], [[17], [18], [1], [19]])],
    "Green": [Race("United States Senator", "GRE", ["WRITE IN"], [[1], [0], [0], [0]])],
    "Questions & Issues": [Race("#1 Grandview Heights Tax Levy", "", ["Yes", "No"],
                                [[20, 25], [0, 0], [0, 0], [12, 15]])],
}  # fmt: skip


@dataclass
class Workbook2016:
    sheets: dict[str, list[Race]] = field(default_factory=lambda: dict(SHEETS))
    bad_turnout_sheet: str | None = None  # this sheet's turnout disagrees with the others
    stray_trailer: bool = False  # an unexpected labeled row after the totals
    unmerged_choice: bool = False  # a second choice column that no contest name covers

    def _header(
        self, name: str, races: list[Race]
    ) -> tuple[list[list[object]], list[tuple[int, int]]]:
        """Three header rows and the row-1 merges (0-based first, last column) per race."""
        ids = IDS + (["COUNTY NUMBER", "PRECINCT CODE"] if name == "Green" else [])
        rows: list[list[object]] = [[""] * len(ids) for _ in range(3)]
        rows[1][: len(IDS) - 1] = IDS[:-1]
        columns: list[tuple[object, object, object]] = [("", "", "PRECINCT NAME")]
        columns += [("", t, "") for t in TURNOUT]
        merges = []
        for race in races:
            start = len(rows[0]) + len(columns)
            columns += [
                (race.name if i == 0 else "", lab, race.code) for i, lab in enumerate(race.labels)
            ]
            if len(race.labels) > 1 and not (self.unmerged_choice and name == "Democratic"):
                merges.append((start, start + len(race.labels) - 1))
        for col in columns:
            for r in range(3):
                rows[r].append(col[r])
        return rows, merges

    def _data(self, name: str, races: list[Race]) -> list[list[object]]:
        data = []
        for s, (code, split, pname, *turnout) in enumerate(SPLITS):
            ids_row: list[object] = [
                10,
                1,
                code,
                split,
                "LID# 1",
                "COLUMBUS",
                "",
                3,
                15,
                18,
                "",
                "",
                "",
            ]
            ids_row += [25, "AAN"] if name == "Green" else []
            t = list(turnout)
            if name == self.bad_turnout_sheet and s == 0:
                t[0] += 1
            data.append([*ids_row, pname, *t, *[v for race in races for v in race.votes[s]]])
        return data

    def _trailer(self, data: list[list[object]], name_col: int, width: int) -> list[list[object]]:
        sums = [sum(r[c] for r in data) if c > name_col else "" for c in range(width)]  # type: ignore[misc]
        only = [*[""] * name_col, "FRANKLIN COUNTY ONLY", *sums[name_col + 1 : name_col + 6]]
        only += [""] * (width - len(only))
        filtered = [*[""] * name_col, "FRANKLIN COUNTY FILTERED TOTALS", *sums[name_col + 1 :]]
        trailer = [[""] * width, only, [""] * width, filtered]
        if self.stray_trailer:
            trailer.append([*[""] * name_col, "GRAND TOTAL", *sums[name_col + 1 :]])
        return trailer

    def _sheet(
        self, ws: openpyxl.worksheet.worksheet.Worksheet, name: str, races: list[Race]
    ) -> None:
        header, merges = self._header(name, races)
        data = self._data(name, races)
        name_col = header[2].index("PRECINCT NAME")
        for row in [*header, *data, *self._trailer(data, name_col, len(header[0]))]:
            ws.append(row)
        for a, b in merges:
            ws.merge_cells(start_row=1, start_column=a + 1, end_row=1, end_column=b + 1)

    def write(self, path: Path) -> Path:
        wb = openpyxl.Workbook()
        first = wb.active
        assert first is not None
        wb.remove(first)
        for name, races in self.sheets.items():
            self._sheet(wb.create_sheet(name), name, races)
        wb.save(path)
        return path
