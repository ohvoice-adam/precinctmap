"""De-identified address -> precinct table from the Franklin County BOE voter file.

County format (sample: data/samples/VOTERFILE.TXT): tab-delimited, 88 columns. Queries name
only the address, precinct, city, and council-district columns; DuckDB's projection pushdown
skips the rest, so no other field reaches Python or the store. Names, voter IDs, birth
dates, party, registration and vote history are never read, stored, or logged. Rows
collapse to one record per street address; per-address voter counts are not kept.
"""

from dataclasses import dataclass
from pathlib import Path

import duckdb
import pandas as pd

from precinctmap.ingest.errors import LayoutError, UnknownLayoutError

ADAPTER = "fcboe_voterfile_county_v1"
READ_COLUMNS = (
    "HOUSE NO",
    "RES APT",
    "RES STREET",
    "RES ZIP",
    "PRECINCT",
    "CITY OR VILLAGE",
    "CITY COUNCIL WARD/DISTRICT",
)
LAYOUT_MARKERS = ("PRECINCT NAME WITH SPLIT", "PRECINCT SPLIT")  # county (not SOS) format
COLUMBUS_CITY_CODE = "COL"

_AGGREGATE = """
WITH src AS (
    SELECT upper(trim(coalesce("HOUSE NO", ''))) AS house_no,
           upper(regexp_replace(trim(coalesce("RES STREET", '')), '\\s+', ' ', 'g')) AS street,
           left(trim(coalesce("RES ZIP", '')), 5) AS zip5,
           nullif(upper(trim(coalesce("RES APT", ''))), '') AS apt,
           trim("PRECINCT") AS precinct_code,
           trim(coalesce("CITY OR VILLAGE", '')) AS city_code,
           CASE WHEN trim(coalesce("CITY OR VILLAGE", '')) = $col
                THEN regexp_extract(trim(coalesce("CITY COUNCIL WARD/DISTRICT", '')),
                                    '^([1-9])(st|nd|rd|th)$', 1) END AS council
    FROM read_csv($path, delim = '\t', header = true, all_varchar = true, quote = '')
)
SELECT zip5, house_no, street,
       mode(precinct_code) AS precinct_code,
       count(DISTINCT precinct_code)::INTEGER AS precinct_codes,
       nullif(mode(council), '') AS council_district,
       mode(city_code) AS city_code,
       greatest(count(DISTINCT apt), 1)::INTEGER AS units_with_voters
FROM src
WHERE house_no <> '' AND street <> '' AND zip5 <> '' AND precinct_code IS NOT NULL
GROUP BY zip5, house_no, street
"""


@dataclass(frozen=True)
class AddressRead:
    frame: pd.DataFrame
    rows_read: int
    rows_without_address: int


def _header(path: Path) -> list[str]:
    with path.open(encoding="utf-8", errors="replace") as f:
        return f.readline().rstrip("\r\n").split("\t")


def read_voter_addresses(con: duckdb.DuckDBPyConnection, path: Path) -> AddressRead:
    header = _header(path)
    if not all(m in header for m in LAYOUT_MARKERS):
        raise UnknownLayoutError(f"{path.name}: not the county voter file layout (tab-delimited)")
    missing = [c for c in READ_COLUMNS if c not in header]
    if missing:
        raise LayoutError(f"{path.name}: missing columns {missing}")
    frame = con.execute(_AGGREGATE, {"path": str(path), "col": COLUMBUS_CITY_CODE}).df()
    counts = con.execute(
        "SELECT count(*), count(*) FILTER (WHERE coalesce(trim(\"HOUSE NO\"), '') = ''"
        " OR coalesce(trim(\"RES STREET\"), '') = '') FROM read_csv($path, delim = '\t',"
        " header = true, all_varchar = true, quote = '')",
        {"path": str(path)},
    ).fetchone()
    if counts is None or counts[0] == 0:
        raise LayoutError(f"{path.name}: no rows")
    return AddressRead(frame, int(counts[0]), int(counts[1]))
