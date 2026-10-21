"""Write tests/golden/official_totals.json from the BOE's certified exports.

Deliberately independent of the precinctmap adapters: reads with openpyxl, finds a column by its
raw row-1 contest and row-3 choice labels, and takes the BOE's own COUNTY TOTALS (ZZZ) row.
Franklin precinct total = rows with registered voters > 0; the rest are other counties.

Usage: uv run python scripts/extract_official_totals.py
"""

import json
import sys
from pathlib import Path

import openpyxl

SAMPLES = Path("data/samples")
OUT = Path("tests/golden/official_totals.json")

# (election_id, file, contest as printed in row 1, choice as printed in row 3, columbus-only)
PICKS = [
    (
        "franklin-2024-03-19-primary",
        "2024-Election-Results-CSV.xlsx",
        "Dem For U.S. Senator -",
        "Sherrod Brown",
        False,
    ),
    (
        "franklin-2024-03-19-primary",
        "2024-Election-Results-CSV.xlsx",
        "Rep For U.S. Senator -",
        "Bernie Moreno",
        False,
    ),
    (
        "franklin-2024-11-05-general",
        "Official-Results-by-Precinct.xlsx",
        "For President and Vice President -",
        "Dem Kamala D. Harris",
        False,
    ),
    (
        "franklin-2024-11-05-general",
        "Official-Results-by-Precinct.xlsx",
        "For President and Vice President -",
        "Rep Donald J. Trump",
        False,
    ),
    (
        "franklin-2024-11-05-general",
        "Official-Results-by-Precinct.xlsx",
        "#1 State Issue 1 -",
        "YES",
        False,
    ),
    (
        "franklin-2025-05-06-primary",
        "2025-Primary-Election-Official-Precinct-Results.xlsx",
        "For Member of Council (District 7) City of Columbus",
        "Tiara Ross",
        True,
    ),
    (
        "franklin-2025-11-04-general",
        "2025-General-Election_EXPORT_Official.xlsx",
        "For Member of Council (District 7) City of Columbus",
        "Jesse Vogel",
        True,
    ),
    (
        "franklin-2025-11-04-general",
        "2025-General-Election_EXPORT_Official.xlsx",
        "#5 Proposed Bond Issue - Safety, Health, Infrustructure City of Columbus",
        "For the Bond Issue",
        True,
    ),
    (
        "franklin-2024-11-05-general",
        "Official-Results-by-Precinct.xlsx",
        "For Representative to Congress (15th District)",
        "Rep Mike Carey",
        False,
    ),
    (
        "franklin-2026-05-05-primary",
        "2026-Primary-Election_EXPORT_Official.xlsx",
        "Dem For Representative to Congress (15th District)",
        "Adam C. Miller",
        False,
    ),
    (
        "franklin-2026-05-05-primary",
        "2026-Primary-Election_EXPORT_Official.xlsx",
        "Dem For Governor and Lieutenant Governor -",
        "Amy Acton",
        False,
    ),
]


def _num(v: object) -> int:
    return 0 if v in (None, "") else int(v)  # type: ignore[call-overload]


def extract(path: Path, contest: str, choice: str) -> dict[str, int]:
    rows = list(openpyxl.load_workbook(path, read_only=True, data_only=True).active.values)  # type: ignore[union-attr]
    cols = [
        j
        for j, (a, c) in enumerate(zip(rows[0], rows[2], strict=True))
        if a == contest and c == choice
    ]
    if len(cols) != 1:
        sys.exit(f"{path.name}: found {len(cols)} columns for {contest!r} / {choice!r}")
    j = cols[0]
    total = next(r for r in rows if r[1] == "ZZZ")
    data = [r for r in rows[3:] if r[1] != "ZZZ"]
    franklin = sum(_num(r[j]) for r in data if _num(r[3]) > 0)
    return {
        "county_total_row": _num(total[j]),
        "franklin_precincts": franklin,
        "other_counties": sum(_num(r[j]) for r in data if _num(r[3]) == 0),
    }


def main() -> None:
    out = []
    for election, file, contest, choice, columbus in PICKS:
        values = extract(SAMPLES / file, contest, choice)
        assert values["franklin_precincts"] + values["other_counties"] == values["county_total_row"]
        out.append(
            {
                "election_id": election,
                "file": file,
                "contest_raw": contest,
                "choice_raw": choice,
                "columbus_only": columbus,
                **values,
            }
        )
    OUT.write_text(json.dumps(out, indent=2) + "\n")
    print(f"wrote {len(out)} totals to {OUT}")


if __name__ == "__main__":
    main()
