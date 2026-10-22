"""A tiny synthetic FCBOE "classic" (2020-layout) workbook; see fcboe_classic_2020.

Precincts COLUMBUS 01-A, COLUMBUS 01-B and BLENDON-A (a township precinct: ward is the number
0), plus a Delaware County row. Contests: the same Congress race on the Dem and Rep ballots,
two Dem county central committee races sharing a name (ward COLUMBUS 01, and BLENDON-A), a
write-in central committee race, and a joint library levy with Delaware County votes.
"""

from dataclasses import dataclass, field
from pathlib import Path

import openpyxl

PRECINCTS = [("COLUMBUS 01-A", "010", "01", "A"), ("COLUMBUS 01-B", "010", "01", "B"),
             ("BLENDON-A", "030", 0, "A")]  # fmt: skip
COUNTY_ROWS = ["Delaware County"]
CYCLE = ["ABSENTEE", "EARLY VOTE", "PROVISIONAL", "TOTAL"]


@dataclass
class Contest:
    name: str
    party: str
    labels: list[str]
    votes: dict[int, list[int]]  # data-row index -> total per choice (rows not listed: zeros)


CONTESTS = [
    Contest(
        "Representative to Congress 3rd District",
        "Dem",
        ["Alice Avery", "OVER VOTES", "UNDER VOTES"],
        {0: [40, 0, 2], 1: [30, 1, 1], 2: [20, 0, 0]},
    ),
    Contest(
        "Representative to Congress 3rd District",
        "Rep",
        ["Bob Brown", "OVER VOTES", "UNDER VOTES"],
        {0: [25, 0, 1], 1: [35, 0, 0], 2: [45, 0, 3]},
    ),
    Contest(
        "Member of County Central Committee",
        "Dem",
        ["Carol Cruz", "OVER VOTES", "UNDER VOTES"],
        {0: [12, 0, 5], 1: [9, 0, 4]},
    ),
    Contest(
        "Member of County Central Committee",
        "Dem",
        ["Dan Diaz", "OVER VOTES", "UNDER VOTES"],
        {2: [8, 0, 2]},
    ),
    Contest(
        "WI Dem Member of County Central Committee",
        "Dem",
        ["Write-in", "OVER VOTES", "UNDER VOTES"],
        {2: [1, 0, 9]},
    ),
    Contest(
        "Joint Library Levy",
        "Non",
        ["Yes", "No", "OVER VOTES", "UNDER VOTES"],
        {0: [50, 20, 0, 4], 1: [44, 30, 0, 2], 2: [33, 40, 1, 3], 3: [70, 60, 0, 5]},
    ),
]


@dataclass
class ClassicSheet:
    contests: list[Contest] = field(default_factory=lambda: list(CONTESTS))
    break_cycle: bool = False  # mislabel one vote-type header
    bad_part: bool = False  # TOTAL != ABSENTEE + EARLY + PROVISIONAL in one cell
    filtered_differs: bool = False  # 'Filtered Totals' disagrees with 'Total Votes'

    def _choice_columns(self) -> list[tuple[Contest, int, str]]:
        return [(k, i, label) for k in self.contests for i, label in enumerate(k.labels)]

    def _header(self) -> list[list[object]]:
        ids = ["PRECINCT NAME", "SUBDIVISION", "WARD", "PRECINCT", "CONGRESS", "SENATE", "HOUSE",
               "SCHOOL", "FIRE", "POLICE", ""]  # fmt: skip
        rows: list[list[object]] = [[""] * 11 for _ in range(3)] + [ids]
        reg = ["TOTAL", "DEMOCRATIC", "REPUBLICAN", "LIBERTARIAN", "NONPARTIAN"]
        for j, label in enumerate(reg):
            (
                rows[0].append(""),
                rows[1].append(""),
                rows[2].append("REGISTERED VOTERS" if j == 0 else ""),
            )
            rows[3].append(label)
        for name in ("TOTAL", "DEMOCRATIC", "REPUBLICAN", "LIBERTARIAN", "NONPARTISAN", "BLANK"):
            for i, vt in enumerate(CYCLE):
                rows[0].append(f"{name} BALLOTS CAST" if i == 0 else ""), rows[1].append("")
                rows[2].append(""), rows[3].append(vt)
        previous = None
        for k, i, label in self._choice_columns():
            for j, vt in enumerate(CYCLE):
                anchor = j == 0 and (k is not previous or i % 2 == 0)  # names repeat in blocks
                rows[0].append(k.name if anchor else ""), rows[1].append(k.party if j == 0 else "")
                rows[2].append(label if j == 0 else ""), rows[3].append(vt)
            previous = k
        if self.break_cycle:
            rows[3][41] = "EARLY VOTES"
        return rows

    def _data_row(self, r: int) -> list[object]:
        if r < len(PRECINCTS):
            name, sub, ward, pct = PRECINCTS[r]
            line: list[object] = [
                name,
                sub,
                ward,
                pct,
                "03",
                "15",
                "18",
                "COLUMBUS CSD",
                "NONE",
                "NONE",
                "",
            ]
            line += [100, 40, 50, 0, 10]  # registered by party
            ballots = [90, 60, 25, 0, 5]
        else:
            line = [COUNTY_ROWS[r - len(PRECINCTS)], "", "", "", "", "", "", "", "", "", ""]
            line += [0, 0, 0, 0, 0]
            ballots = [0, 0, 0, 0, 0]
        for b in [*ballots, 1 if r < len(PRECINCTS) else 0]:
            line += [b // 2, b - b // 2, 0, b]
        for k, i, _ in self._choice_columns():
            v = k.votes.get(r, [0] * len(k.labels))[i]
            line += [v // 2, v - v // 2, 0, v]
        return line

    def grid(self) -> list[list[object]]:
        header = self._header()
        data = [self._data_row(r) for r in range(len(PRECINCTS) + len(COUNTY_ROWS))]
        if self.bad_part:
            data[0][43] = 999
        width = len(header[0])
        totals: list[object] = [""] * 11 + [
            sum(row[c] for row in data if isinstance(row[c], int)) for c in range(11, width)
        ]
        filtered = list(totals)
        if self.filtered_differs:
            filtered[11] = int(totals[11]) + 1  # type: ignore[call-overload]
        label = lambda text: [""] * 8 + [text] + [""] * (width - 9)  # noqa: E731
        blank = [""] * width
        return [
            *header,
            *data,
            blank,
            label("Total Votes"),
            totals,
            label("Filtered Totals"),
            filtered,
        ]

    def write(self, path: Path) -> Path:
        wb = openpyxl.Workbook()
        ws = wb.active
        assert ws is not None
        for row in self.grid():
            ws.append(row)
        wb.save(path)
        return path
