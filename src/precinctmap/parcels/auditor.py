"""Franklin County Auditor parcel CSV (sample: data/samples/Parcel.csv, 67 columns).

Data dictionary: data/samples/parcel-csv-description-of-fields.pdf. The file's header differs
from the dictionary in places (PARCEL ID for PID, TRANDT, NBRHD); the header is authoritative.
POINT_X / POINT_Y are NAD83 Ohio State Plane South, US feet (EPSG:3735).

Owner names and mailing addresses (NAME1-3, OWNER_ADD1-2, MAILAD1-4) are dropped at read and
never stored. Some legal-description fields contain stray quotes that merge two fields; those
rows are rebuilt from the intact fields on either side and every repair is logged.
"""

import csv
import json
import re
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from precinctmap.ingest.errors import LayoutError, UnknownLayoutError
from precinctmap.parcels.tenure import derive

ADAPTER = "fca_parcel_csv_v2"  # v2: residential / rental flags and grade score
HEADER = [
    "PARCEL ID",
    "AEXMLND",
    "AEXMBLD",
    "AEXMTOT",
    "APPRLND",
    "APPRBLD",
    "APPRTOT",
    "AUDMAP",
    "AUDRTG",
    "LANDUSE",
    "CAUV",
    "SCHOOL",
    "MAILAD1",
    "MAILAD2",
    "MAILAD3",
    "MAILAD4",
    "TRANDT",
    "TRANYR",
    "NAME1",
    "NAME2",
    "NAME3",
    "OWNER_ADD1",
    "OWNER_ADD2",
    "NBRHD",
    "FLOOD",
    "PCLASS",
    "NOCARDS",
    "ACREA",
    "PRICE",
    "ANN_TAX",
    "STHNUM",
    "STCONT",
    "STHSFX",
    "STDIRE",
    "STNAME",
    "STSFX",
    "STADDR",
    "USPS_CITY",
    "STATE",
    "ZIPCODE",
    "DESCR1",
    "DESCR2",
    "DESCR3",
    "TAXDESI",
    "VALID",
    "AREA_A",
    "DWELTYP",
    "ROOMS",
    "BATHS",
    "HBATHS",
    "BEDRMS",
    "AIRCOND",
    "CINBRHD",
    "COND",
    "FIREPLC",
    "GRADE",
    "HEIGHT",
    "NOSTORY",
    "YEARBLT",
    "PROPTYP",
    "WALL",
    "TIFMLND",
    "TIFMBLD",
    "POINT_X",
    "POINT_Y",
    "HOMSTD",
    "BANKCODE",
]
OWNER_COLUMNS = frozenset(
    {
        "NAME1",
        "NAME2",
        "NAME3",
        "OWNER_ADD1",
        "OWNER_ADD2",
        "MAILAD1",
        "MAILAD2",
        "MAILAD3",
        "MAILAD4",
    }
)
_DESCR = HEADER.index("DESCR1")  # fields before this parse cleanly in broken rows
_TAIL = len(HEADER) - HEADER.index("TAXDESI")  # fields after DESCR3 have no commas
_PID = re.compile(r"\d{3}-\d{6}")
# Generous box around Franklin County in EPSG:3735 feet; anything outside is a bad point.
BOUNDS = (1_700_000.0, 600_000.0, 1_950_000.0, 840_000.0)

_TYPED = {  # parcels table column -> source column
    "pid": "PARCEL ID",
    "pclass": "PCLASS",
    "landuse": "LANDUSE",
    "taxdesi": "TAXDESI",
    "school": "SCHOOL",
    "site_address": "STADDR",
    "house_no": "STHNUM",
    "city": "USPS_CITY",
    "transfer_date": "TRANDT",
    "homestead": "HOMSTD",
    "dwelling": "DWELTYP",
    "year_built": "YEARBLT",
    "grade": "GRADE",
    "condition": "COND",
}
_NUMERIC = {
    "acres": "ACREA",
    "appraised_total": "APPRTOT",
    "exempt_total": "AEXMTOT",
    "annual_tax": "ANN_TAX",
    "sale_price": "PRICE",
    "rooms": "ROOMS",
    "bedrooms": "BEDRMS",
    "building_value": "APPRBLD",
}


@dataclass
class ParcelRead:
    frame: pd.DataFrame
    rows_read: int
    log: list[tuple[str | None, str, str]] = field(default_factory=list)  # (pid, issue, detail)


def detect(path: Path) -> bool:
    with path.open(encoding="utf-8-sig", newline="") as f:
        return next(csv.reader([f.readline().rstrip("\r\n")]), []) == HEADER


def _repair(raw: str, parsed: list[str]) -> list[str] | None:
    """Rebuild a row whose description fields broke the CSV quoting."""
    plain = raw.split(",")
    if len(parsed) < _DESCR or len(plain) < _DESCR + _TAIL:
        return None
    middle = plain[_DESCR : len(plain) - _TAIL]
    descr = [",".join(middle).replace('"', "").strip(), "", ""]
    tail = [v.strip().strip('"') for v in plain[len(plain) - _TAIL :]]  # unquote: not CSV-parsed
    row = parsed[:_DESCR] + descr + tail
    return row if len(row) == len(HEADER) else None


def _rows(path: Path, log: list[tuple[str | None, str, str]]) -> tuple[list[list[str]], int]:
    rows: list[list[str]] = []
    read = 0
    with path.open(encoding="utf-8-sig", newline="") as f:
        f.readline()
        for n, raw in enumerate(f, start=2):
            raw = raw.rstrip("\r\n")
            if not raw:
                continue
            read += 1
            row = next(csv.reader([raw]))
            if len(row) != len(HEADER):
                fixed = _repair(raw, row)
                pid = row[0] if row else None
                if fixed is None:
                    log.append(
                        (pid, "rejected_row", f"line {n}: {len(row)} fields, not repairable")
                    )
                    continue
                log.append(
                    (pid, "repaired_row", f"line {n}: {len(row)} fields rebuilt to {len(HEADER)}")
                )
                row = fixed
            rows.append(row)
    return rows, read


def _clean(df: pd.DataFrame, log: list[tuple[str | None, str, str]]) -> pd.DataFrame:
    bad_pid = ~df["PARCEL ID"].str.fullmatch(_PID)
    for pid in df.loc[bad_pid, "PARCEL ID"]:
        log.append((pid, "rejected_row", "parcel id is not DDD-NNNNNN"))
    dup = df["PARCEL ID"].duplicated(keep="first") & ~bad_pid
    for pid in df.loc[dup, "PARCEL ID"]:
        log.append((pid, "rejected_row", "duplicate parcel id (first kept)"))
    df = df.loc[~bad_pid & ~dup].copy()
    x = pd.to_numeric(df["POINT_X"], errors="coerce")
    y = pd.to_numeric(df["POINT_Y"], errors="coerce")
    xmin, ymin, xmax, ymax = BOUNDS
    ok = x.between(xmin, xmax) & y.between(ymin, ymax)
    for pid in df.loc[~ok, "PARCEL ID"]:
        log.append((pid, "bad_coordinates", "missing or outside the county; address only"))
    df["x_ft"], df["y_ft"] = x.where(ok), y.where(ok)
    return df


def _street(df: pd.DataFrame) -> pd.Series:
    parts = (
        df["STDIRE"].str.strip() + " " + df["STNAME"].str.strip() + " " + df["STSFX"].str.strip()
    )
    return parts.str.upper().str.replace(r"\s+", " ", regex=True).str.strip()


def read_parcels(path: Path) -> ParcelRead:
    if not detect(path):
        raise UnknownLayoutError(f"{path.name}: header is not the auditor parcel CSV layout")
    log: list[tuple[str | None, str, str]] = []
    rows, read = _rows(path, log)
    if not rows:
        raise LayoutError(f"{path.name}: no parcel rows")
    df = _clean(pd.DataFrame(rows, columns=HEADER), log)
    out = pd.DataFrame({k: df[v].str.strip() for k, v in _TYPED.items()})
    out["street"] = _street(df).values
    out["zip5"] = df["ZIPCODE"].str.strip().str[:5].values
    for k, v in _NUMERIC.items():
        out[k] = pd.to_numeric(df[v].str.strip(), errors="coerce").values
    kept = [c for c in HEADER if c not in OWNER_COLUMNS and c not in _TYPED.values()]
    out["attributes"] = [json.dumps(r, separators=(",", ":")) for r in df[kept].to_dict("records")]
    derived = derive(df)  # owner columns are still present here; only flags leave this call
    for col in derived.columns:
        out[col] = derived[col].values
    out["x_ft"], out["y_ft"] = df["x_ft"].values, df["y_ft"].values
    return ParcelRead(out.reset_index(drop=True), read, log)
