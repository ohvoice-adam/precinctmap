"""Synthetic auditor parcel CSV and county voter file for the mini-county (tests/fixtures/geo.py).

Parcels (x = feet east of the mini-county origin; y = 500):
  010-000001  100 MAIN ST        x 500   COLUMBUS 01-A, district 1, voter agrees
  010-000002  200 MAIN ST        x 1600  COLUMBUS 01-B, district 2, voter agrees
  010-000003  300 MAIN ST        x 2500  BLENDON-A (not Columbus)
  010-000004  (no address)       x 5010  10 ft east of OBETZ-D -> nearest precinct
  010-000005  400 - 404 OAK ST   x 1200  01-B; voter 402 (same side) agrees, 403 ignored
  010-000006  500 MAIN ST        x 600   01-A; broken quotes in the legal description (repaired)
  010-000007  700 PINE ST        x 700   01-A by geometry, voter file says 01-B -> disagreement
  010-000008  10 EDGE RD         x -10   10 ft west of 01-A; outside districts; voter council 1
  010-000009  20 EDGE RD         x -20   same, no voter address -> nearest district

  010-000010  900 OAK AVE        x 1300  01-B; apartment building (C / 401), units from census block
  010-000011  800 ELM ST         x 2100  BLENDON-A by geometry; voter file says 01-B (Columbus,
                                         district 2) -> override; municipality follows

Ownership (rental flags): 010-000002 owner lives elsewhere; 010-000003 owned by an LLC;
010-000005 has no owner address (unknown); every other owner lives at the parcel.
"""

import csv
from pathlib import Path

from precinctmap.parcels.auditor import HEADER
from tests.fixtures.geo import X0, Y0

PARCELS = [
    ("010-000001", "100", "MAIN", "ST", 500),
    ("010-000002", "200", "MAIN", "ST", 1600),
    ("010-000003", "300", "MAIN", "ST", 2500),
    ("010-000004", "", "", "", 5010),
    ("010-000005", "400", "OAK", "ST", 1200),
    ("010-000006", "500", "MAIN", "ST", 600),
    ("010-000007", "700", "PINE", "ST", 700),
    ("010-000008", "10", "EDGE", "RD", -10),
    ("010-000009", "20", "EDGE", "RD", -20),
    ("010-000010", "900", "OAK", "AVE", 1300),
    ("010-000011", "800", "ELM", "ST", 2100),
]
APARTMENTS = {"010-000010": {"PCLASS": "C", "LANDUSE": "401", "DWELTYP": "", "APPRBLD": "900000"}}


OWNERSHIP = {
    "010-000002": {"OWNER_ADD1": "9 FAR AWAY RD", "OWNER_ADD2": "DAYTON OH 45402"},
    "010-000003": {"NAME1": "RENTCO HOLDINGS LLC", "OWNER_ADD1": "300 MAIN ST"},
    "010-000005": {"OWNER_ADD1": "", "OWNER_ADD2": ""},
}
GRADES = {"010-000001": "C", "010-000002": "C+1", "010-000003": "B", "010-000005": "D+2"}
BUILDING = {"010-000001": "100000", "010-000002": "200000", "010-000003": "300000"}


def write_parcel_csv(path: Path) -> Path:
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        f.write(",".join(HEADER) + "\n")
        w = csv.writer(f, quoting=csv.QUOTE_ALL)
        for pid, num, name, sfx, x in PARCELS:
            row = dict.fromkeys(HEADER, "")
            row.update(
                {
                    "PARCEL ID": pid,
                    "PCLASS": "R",
                    "STHNUM": num,
                    "STNAME": name,
                    "STSFX": sfx,
                    "STADDR": f"{num} {name} {sfx}".strip(),
                    "USPS_CITY": "COLUMBUS",
                    "ZIPCODE": "43215",
                    "NAME1": "OWNER PERSON",
                    "MAILAD1": "1 SECRET LN",
                    "APPRTOT": "100000",
                    "POINT_X": f"{X0 + x}",
                    "POINT_Y": f"{Y0 + 500}",
                }
            )
            row.update(
                {
                    "DWELTYP": "1",
                    "GRADE": GRADES.get(pid, "C"),
                    "APPRBLD": BUILDING.get(pid, "150000"),
                    "OWNER_ADD1": row["STADDR"],
                    "OWNER_ADD2": "COLUMBUS OH 43215",
                }
            )
            row.update(OWNERSHIP.get(pid, {}))
            row.update(APARTMENTS.get(pid, {}))
            if pid == "010-000005":
                row.update(
                    {"STHNUM": "400", "STCONT": "-", "STHSFX": "404", "STADDR": "400 - 404 OAK ST"}
                )
            w.writerow([row[h] for h in HEADER])
    _break_quotes(path, "010-000006")
    return path


def _break_quotes(path: Path, pid: str) -> None:
    """Reproduce the real file's stray quotes that merge two description fields."""
    text = path.read_text(encoding="utf-8-sig").splitlines()
    out = []
    for line in text:
        if line.startswith(f'"{pid}"'):
            parts = line.split(",")
            d = HEADER.index("DESCR1")
            parts[d], parts[d + 1] = '"POND "VILLAGES"', '"SECTION 9""'
            line = ",".join(parts)
        out.append(line)
    path.write_text("\n".join(out) + "\n", encoding="utf-8-sig")


VOTER_COLUMNS = [
    "LAST NAME",
    "DATE OF BIRTH",
    "HOUSE NO",
    "HOUSE NO FRAC",
    "RES APT",
    "RES STREET",
    "RES ZIP",
    "PRECINCT",
    "PRECINCT SPLIT",
    "PRECINCT NAME WITH SPLIT",
    "CITY OR VILLAGE",
    "CITY COUNCIL WARD/DISTRICT",
    "VoterID",
]
VOTERS = [  # (house, street, zip, precinct code, city code, council)
    ("100", "MAIN ST", "43215", "01001A", "COL", "1st"),
    ("100", "MAIN ST", "43215", "01001A", "COL", "1st"),  # second voter at the same address
    ("200", "MAIN ST", "43215", "01001B", "COL", "2nd"),
    ("300", "MAIN ST", "43215", "03001A", "BLE", ""),
    ("402", "OAK ST", "43215", "01001B", "COL", "1st"),
    ("403", "OAK ST", "43215", "03001A", "BLE", ""),
    ("700", "PINE ST", "43215", "01001B", "COL", "1st"),
    ("10", "EDGE RD", "43215", "01001A", "COL", "1st"),
    ("800", "ELM ST", "43215", "01001B", "COL", "2nd"),
]


def write_voter_file(path: Path) -> Path:
    lines = ["\t".join(VOTER_COLUMNS)]
    for i, (hn, street, zipc, code, city, council) in enumerate(VOTERS):
        lines.append(
            "\t".join(
                [
                    "SECRETNAME",
                    "01/01/1970",
                    hn,
                    "",
                    "",
                    street,
                    zipc,
                    code,
                    "01",
                    f"X {code}",
                    city,
                    council,
                    f"OH{i:08d}",
                ]
            )
        )
    path.write_text("\r\n".join(lines) + "\r\n")
    return path
