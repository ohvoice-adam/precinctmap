"""Tiny synthetic 2016-general and 2020-general workbooks (see fcboe_general_2016/2020).

Precincts COLUMBUS 01-A, COLUMBUS 01-B and BLENDON-A. The 2016 file splits COLUMBUS 01-B in two
and has a Delaware County row for the joint levy; the 2020 file has one row per precinct and
a State Board race whose first name block lacks the district ('... Education', then '... 6th').
"""

from dataclasses import dataclass, field
from pathlib import Path

import openpyxl

# --- 2016 general ---------------------------------------------------------------------------
SPLITS_2016 = [  # name, name with split, code, registered, voters
    ("COLUMBUS 01-A", "COLUMBUS 01-A 1", "01001A", 100, 70),
    ("COLUMBUS 01-B", "COLUMBUS 01-B 1", "01001B", 80, 50),
    ("COLUMBUS 01-B", "COLUMBUS 01-B 2", "01001B", 20, 10),
    ("BLENDON-A", "BLENDON-A 1", "03000A", 60, 40),
]
RACES_2016 = [  # name, [(party code, label)], votes per split row, Delaware County votes
    ("President and Vice President",
     [("DEM", "Hillary Clinton"), ("REP", "Donald J. Trump"), ("", "Write In")],
     [[40, 25, 1], [30, 18, 0], [6, 4, 0], [15, 22, 1]], [0, 0, 0]),
    ("#1 Joint Library Levy", [("", "For the Tax Levy"), ("", "Against the Tax Levy")],
     [[30, 20], [0, 0], [0, 0], [10, 20]], [55, 45]),
]  # fmt: skip


@dataclass
class General2016:
    bad_subtotal: bool = False  # FRANKLIN COUNTY row disagrees with the splits
    stray_label: str | None = None  # an unexpected labeled row in the trailer

    def _write(self, ws: openpyxl.worksheet.worksheet.Worksheet) -> None:
        ids = ["PRECINCT NAME", "PRECINCT NAME WITH SPLIT", "PRECINCT CODE"] + [""] * 24
        ids += ["PRECINCT NAME", "REGISTERED VOTERS", "TOTAL VOTERS"]
        names, parties, labels, merges = [], [], [], []
        for name, choices, _, _ in RACES_2016:
            merges.append((len(ids) + len(labels), len(ids) + len(labels) + len(choices) - 1))
            for i, (code, label) in enumerate(choices):
                names.append(name if i == 0 else ""), parties.append(code), labels.append(label)
        width = len(ids) + len(labels)
        ws.append([f"{i + 1:03d}" for i in range(width)])
        ws.append([""] * len(ids) + names)
        ws.append([""] * len(ids) + parties)
        ws.append(ids + labels)
        data = []
        for s, (name, split, code, reg, voters) in enumerate(SPLITS_2016):
            votes = [v for _, _, rows, _ in RACES_2016 for v in rows[s]]
            data.append([name, split, code] + [""] * 24 + [split, reg, voters, *votes])
        county = (
            [""] * 25 + [25, "", "Delaware County", 0, 0] + [v for *_, d in RACES_2016 for v in d]
        )
        sums = [sum(r[c] for r in data) for c in range(28, width)]
        franklin = (
            [""] * 27
            + ["FRANKLIN COUNTY"]
            + [s + (1 if self.bad_subtotal and i == 0 else 0) for i, s in enumerate(sums)]
        )
        overlap = [""] * 27 + ["OVERLAP COUNTIES ONLY"] + county[28:]
        totals = (
            [""] * 27 + ["COUNTY TOTALS"] + [a + b for a, b in zip(sums, county[28:], strict=True)]
        )
        rows = [*data, franklin, county]
        if self.stray_label:
            rows.append([""] * 27 + [self.stray_label] + [0] * (width - 28))
        for row in [*rows, overlap, totals]:
            ws.append(row)
        for a, b in merges:
            ws.merge_cells(start_row=2, start_column=a + 1, end_row=2, end_column=b + 1)

    def write(self, path: Path) -> Path:
        wb = openpyxl.Workbook()
        ws = wb.active
        assert ws is not None
        ws.title = "General 2016"
        self._write(ws)
        wb.save(path)
        return path


# --- 2020 general ---------------------------------------------------------------------------
PRECINCTS_2020 = [
    ("010", "01", "A", "01001A", "COLUMBUS 01-A", 100),
    ("010", "01", "B", "01001B", "COLUMBUS 01-B", 90),
    ("030", "00", "A", "03000A", "BLENDON-A", 60),
]
CYCLE = ["Absentee", "Early Vote", "Election Day", "Provisoinal", "TOTAL"]


@dataclass
class General2020:
    # contest name per choice block ('' = merged continuation), label, totals per precinct
    races: list[tuple[str, str, list[int]]] = field(default_factory=lambda: [
        ("President and Vice President", "Dem Joseph R. Biden", [50, 40, 20]),
        ("", "Rep Donald J. Trump", [20, 30, 35]),
        ("President and Vice President", "OVER VOTES", [0, 1, 0]),
        ("", "UNDER VOTES", [2, 1, 1]),
        ("State Board of Education", "Antoinette Miranda", [30, 25, 0]),
        ("State Board of Education 6th", "Alice Nicks", [20, 20, 0]),
        ("State Board of Education 6th", "OVER VOTES", [0, 0, 0]),
        ("", "UNDER VOTES", [22, 27, 0]),
    ])  # fmt: skip
    bad_part: bool = False
    filtered_differs: bool = False

    def _header(self) -> list[list[object]]:
        ids = (
            ["DISTRICT NO", "WARD NO", "PRECINCT NUMBER", "PRECINCT CODE"]
            + [""] * 21
            + ["PRECINCT NAME", ""]
        )
        rows: list[list[object]] = [[""] * len(ids) for _ in range(4)] + [ids]
        (
            rows[2].append("REGISTERED VOTERS"),
            rows[0].append(""),
            rows[1].append(""),
            rows[3].append(""),
            rows[4].append(""),
        )
        for label in ("BALLOTS CAST", "BALLOTS CAST BLANK"):
            for i, vt in enumerate(CYCLE):
                for r, v in enumerate(["", label if i == 0 else "", "", "", vt]):
                    rows[r].append(v)
        for name, label, _ in self.races:
            for i, vt in enumerate(CYCLE):
                for r, v in enumerate(
                    [
                        name if i == 0 else "",
                        label if i == 0 else "",
                        "Non" if i == 0 else "",
                        "",
                        vt,
                    ]
                ):
                    rows[r].append(v)
        return rows

    def _data(self) -> list[list[object]]:
        out = []
        for p, (d, w, n, code, name, reg) in enumerate(PRECINCTS_2020):
            line: list[object] = [d, w, n, code] + [""] * 21 + [name, "", reg]
            ballots = reg // 2
            for b in (ballots, 0):
                line += [b // 2, b - b // 2, 0, 0, b]
            for _, _, v in self.races:
                line += [v[p] // 2, v[p] - v[p] // 2, 0, 0, v[p]]
            out.append(line)
        if self.bad_part:
            out[0][27 + 10 + 5] = 999  # first choice's TOTAL in the first precinct
        return out

    def write(self, path: Path) -> Path:
        header, data = self._header(), self._data()
        width = len(header[0])
        totals: list[object] = (
            [""] * 25 + ["TOTALS", ""] + [sum(r[c] for r in data) for c in range(27, width)]
        )  # type: ignore[misc]
        filtered = list(totals)
        filtered[25] = "FILTERED TOTALS"
        if self.filtered_differs:
            filtered[27] = int(filtered[27]) + 1  # type: ignore[call-overload]
        wb = openpyxl.Workbook()
        ws = wb.active
        assert ws is not None
        for row in [*header, *data, [""] * width, totals, filtered]:
            ws.append(row)
        wb.save(path)
        return path
