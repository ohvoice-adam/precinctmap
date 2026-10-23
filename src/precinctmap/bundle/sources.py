"""Where each dataset comes from and how to refresh it, plus its vintage read from the store.

The static part (publisher, update location, cadence, how to load) is written here once; the
vintage (dates, files, checksums) is read from the store at export, so DATA.md always matches
the data in the bundle. Links point to publishers' sites; deep links change, so the notes say
how to find the file there.
"""

from dataclasses import dataclass
from typing import Any

import duckdb


@dataclass(frozen=True)
class Dataset:
    key: str
    title: str
    tables: tuple[str, ...]
    publisher: str
    get_updates: str
    cadence: str
    how_to_load: str
    terms: str
    notes: str = ""


DATASETS: tuple[Dataset, ...] = (
    Dataset(
        "elections", "Election results and turnout",
        ("elections", "source_files", "contests", "choices", "precinct_results", "precinct_sources",
         "precinct_turnout", "out_of_county_results", "normalization_log", "unmatched_precincts",
         "ingest_events"),
        "Franklin County Board of Elections",
        "https://vote.franklincountyohio.gov/ (election results; precinct-level results as .xlsx)",
        "Once per election; unofficial results on election night, then the certified canvass.",
        "Admin page upload, or `precinctmap ingest <file> --review` then `--commit <id>`.",
        "Public records. The original spreadsheets are in this bundle under sources/results/.",
    ),
    Dataset(
        "precincts", "Voting precinct boundaries",
        ("boundary_sets", "features", "feature_codes", "geometry_repairs"),
        "Franklin County Board of Elections (voting precinct GIS layer, VotingPrecinct.shp)",
        "Ask the Franklin County Board of Elections for its current voting precinct shapefile.",
        "When the BOE redraws precincts (annexations, splits); no older vintage is published.",
        "Add the file under data/boundaries/, add a set to config/boundaries.toml, then "
        "`precinctmap boundaries load --replace <set>`.",
        "Public records.",
        "Every election before July 2025 uses the July 2025 map, labeled retroactive.",
    ),
    Dataset(
        "council", "Columbus City Council districts",
        ("boundary_sets", "features"),
        "City of Columbus",
        "https://opendata.columbus.gov/ (search 'City Council Districts')",
        "After redistricting (the 2023 map is the first and current one).",
        "As for precincts: data/boundaries/, config/boundaries.toml, `boundaries load --replace`.",
        "Check the City of Columbus open data terms.",
    ),
    Dataset(
        "tiger",
        "Census geography: county outline, places, townships, ZIP areas (ZCTA), 2020 blocks",
        ("boundary_sets", "features", "census_blocks"),
        "U.S. Census Bureau, TIGER/Line shapefiles",
        "https://www2.census.gov/geo/tiger/ (TIGER<year>/COUNTY, PLACE, COUSUB, ZCTA520; "
        "TIGER2020/TABBLOCK20 for blocks)",
        "Yearly (late summer); 2020 blocks and ZCTA definitions change only with the next census.",
        "Download into data/boundaries/, point config/boundaries.toml at it, `boundaries load "
        "--replace <set>`.",
        "Public domain (U.S. government work).",
        "TIGER places and county subdivisions are used only to cut villages with no precincts "
        "of their own out of their township precincts; they are not stored as separate sets.",
    ),
    Dataset(
        "crosswalks", "Precinct-to-area crosswalks",
        ("precinct_crosswalk", "crosswalk_log"),
        "Derived here from the boundaries and 2020 block population",
        "Rebuilt by `precinctmap boundaries load` whenever a boundary set changes.",
        "With the boundaries.",
        "Built automatically.",
        "Same as the boundaries they come from.",
    ),
    Dataset(
        "census", "Census demographics (American Community Survey 5-year estimates)",
        ("census_releases", "census_files", "census_stats", "census_log"),
        "U.S. Census Bureau, ACS table-based summary file",
        "https://www2.census.gov/programs-surveys/acs/summary_file/ "
        "(<year>/table-based-SF/data/5YRData/)",
        "Yearly, each December (the 2021-2025 release is due December 2026).",
        "`precinctmap census fetch --year <year> --as-of <date>`, then `census load ... --commit` "
        "(see project-docs/census.md).",
        "Public domain (U.S. government work). The filtered county files are in sources/census/.",
    ),
    Dataset(
        "parcels", "Residential property (auditor parcels)",
        ("parcel_files", "parcels", "parcel_assignments", "parcel_log", "parcel_stats"),
        "Franklin County Auditor",
        "https://www.franklincountyauditor.com/ (real estate data downloads: Parcel.csv and its "
        "field-definition PDF)",
        "The auditor refreshes its downloads regularly; values change with each reappraisal.",
        "`precinctmap parcels review <Parcel.csv> --as-of <date>`, then `parcels commit <id> "
        "--replace`.",
        "Public records; check the auditor's download terms before redistributing.",
        "Owner names and mailing addresses are dropped at read and are not in this bundle; only "
        "derived flags (LLC owner, owner elsewhere) are. The original Parcel.csv is not included.",
    ),
    Dataset(
        "voter_addresses", "De-identified voter-file address table",
        ("address_files", "voter_addresses"),
        "Franklin County Board of Elections voter file (county format); the Ohio Secretary of "
        "State also publishes statewide voter files",
        "https://vote.franklincountyohio.gov/ (voter file downloads) or https://www.ohiosos.gov/ "
        "(voter files)",
        "The voter file changes continuously; download a fresh copy before re-matching parcels.",
        "`precinctmap addresses load <VOTERFILE.TXT> --as-of <date> --commit`.",
        "Derived from public records.",
        "One row per street address: house number, street, ZIP, precinct, council district, city "
        "code, and how many distinct unit numbers had a registered voter. No names, voter IDs, "
        "birth dates, party or vote history. Used only to place parcels; the voter file itself is "
        "not included.",
    ),
)  # fmt: skip


def _q(con: duckdb.DuckDBPyConnection, sql: str) -> list[tuple[Any, ...]]:
    return con.execute(sql).fetchall()


_ELECTIONS = (
    "SELECT e.label, e.certified, f.filename, f.sha256 FROM elections e"
    " JOIN source_files f USING (election_id) WHERE f.status = 'active' ORDER BY e.election_date"
)
_SETS = (
    "SELECT boundary_set_id, geography, source, valid_from, valid_to, native_from, loaded_at"
    " FROM boundary_sets ORDER BY geography, valid_from"
)
_GEO_KEY = {
    "precinct": "precincts",
    "municipality": "precincts",
    "ward": "precincts",
    "council_district": "council",
}


def _boundary_line(sid: str, geo: str, src: str, vf: Any, vt: Any, nf: Any, loaded: Any) -> str:
    window = f"used for {vf}" + (f" to {vt}" if vt else " onward")
    drawn = f"; drawn {nf}" if nf else ""
    return f"{sid} ({geo}): {src}; {window}{drawn}; loaded {loaded:%Y-%m-%d}"


def vintages(con: duckdb.DuckDBPyConnection) -> dict[str, list[str]]:
    """Dataset key -> lines describing exactly what is loaded (dates, files, checksums)."""
    out: dict[str, list[str]] = {d.key: [] for d in DATASETS}
    for label, cert, fname, sha in _q(con, _ELECTIONS):
        status = "certified" if cert else "unofficial"
        out["elections"].append(f"{label} ({status}): {fname}, sha256 {sha[:16]}")
    for row in _q(con, _SETS):
        out[_GEO_KEY.get(row[1], "tiger")].append(_boundary_line(*row))
    for pset, tset, n in _q(
        con,
        "SELECT precinct_set_id, target_set_id, count(DISTINCT precinct_name)"
        " FROM precinct_crosswalk GROUP BY 1, 2 ORDER BY 1, 2",
    ):
        out["crosswalks"].append(f"{pset} -> {tset}: {n:,} precincts")
    for vintage, n, people in _q(
        con, "SELECT vintage, count(*), sum(pop) FROM census_blocks GROUP BY 1"
    ):
        out["tiger"].append(f"{vintage} census blocks: {n:,} blocks, {int(people):,} people")
    for label, as_of, n in _q(
        con,
        "SELECT r.label, r.as_of, count(f.table_id) FROM census_releases r"
        " LEFT JOIN census_files f USING (release_id) GROUP BY ALL",
    ):
        out["census"].append(f"{label}, {n} tables, placed on boundaries valid {as_of}")
    for fname, as_of, n in _q(
        con, "SELECT filename, as_of, parcels FROM parcel_files WHERE status = 'active'"
    ):
        out["parcels"].append(f"{fname} as of {as_of}: {n:,} parcels")
    for fname, as_of, n in _q(
        con, "SELECT filename, as_of, addresses FROM address_files WHERE status = 'active'"
    ):
        out["voter_addresses"].append(f"{fname} as of {as_of}: {n:,} addresses")
    return out
