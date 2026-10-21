"""Match parcel site addresses to the de-identified voter-address table.

Exact key: (ZIP5, house number, street). Ranged parcels ('207 - 215 E HUDSON ST') match voter
addresses on the same street and ZIP within the range and on the same side of the street
(same house-number parity: precinct lines often run down street centerlines); the most
common precinct wins.
Voter precinct codes (BOE PRECINCTID) become precinct names via feature_codes of the set.
"""

import duckdb
import pandas as pd

_MATCH = """
WITH p AS (
    SELECT pid, zip5, house_no, street,
           try_cast(regexp_extract(site_address, '^(\\d+)\\s*-\\s*(\\d+)\\s', 1) AS INTEGER) AS lo,
           try_cast(regexp_extract(site_address, '^(\\d+)\\s*-\\s*(\\d+)\\s', 2) AS INTEGER) AS hi
    FROM _parcels
), v AS (
    SELECT a.zip5, a.house_no, a.street, try_cast(a.house_no AS INTEGER) AS n,
           c.feature_id AS precinct, a.council_district, a.units_with_voters AS units
    FROM voter_addresses a
    LEFT JOIN feature_codes c ON c.boundary_set_id = $pset AND c.code = a.precinct_code
    WHERE a.file_id = $file
), exact AS (
    SELECT p.pid, v.precinct, v.council_district, v.units
    FROM p JOIN v ON v.zip5 = p.zip5 AND v.house_no = p.house_no AND v.street = p.street
), ranged AS (
    SELECT p.pid, mode(v.precinct) AS precinct, mode(v.council_district) AS council_district,
           sum(v.units) AS units
    FROM p JOIN v ON v.zip5 = p.zip5 AND v.street = p.street AND v.n BETWEEN p.lo AND p.hi
         AND v.n % 2 = p.lo % 2
    WHERE p.lo IS NOT NULL AND p.hi >= p.lo AND p.pid NOT IN (SELECT pid FROM exact)
    GROUP BY p.pid
)
SELECT pid, precinct AS voter_precinct, council_district AS voter_council, units AS voter_units
FROM exact
UNION ALL
SELECT pid, precinct, council_district, units FROM ranged
"""


def match_addresses(
    con: duckdb.DuckDBPyConnection, parcels: pd.DataFrame, address_file_id: str | None, pset: str
) -> pd.DataFrame:
    """pid-indexed voter_precinct / voter_council / voter_units (empty without an address file).

    voter_units = distinct unit numbers with a registered voter at the matched address(es).
    """
    empty = pd.DataFrame(
        columns=["voter_precinct", "voter_council", "voter_units"], index=pd.Index([], name="pid")
    )
    if address_file_id is None:
        return empty
    con.register("_parcels", parcels[["pid", "zip5", "house_no", "street", "site_address"]])
    try:
        df = con.execute(_MATCH, {"pset": pset, "file": address_file_id}).df()
    finally:
        con.unregister("_parcels")
    df = df.drop_duplicates("pid")  # an exact address shared by two voter rows: first wins
    return df.set_index("pid")[["voter_precinct", "voter_council", "voter_units"]]
