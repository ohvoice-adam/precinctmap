"""ACS table-based summary files: download, filter to one county, read.

The Census Bureau publishes one pipe-delimited file per table for the whole country
(`acsdt5y{year}-{table}.dat`, ~90 MB each), with an estimate (`_E001`) and 90% margin of
error (`_M001`) column per line. `fetch_table` streams a national file and keeps only the
county's block groups (summary level 150), tracts (140) and the county row (050), so the
stored file is small and its sha256 identifies exactly what was used. No API key is needed.
Some tables (e.g. B05002, place of birth and citizenship) are published only down to tracts.
"""

import hashlib
import logging
import re
import urllib.request
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from precinctmap.ingest.errors import UnknownLayoutError

log = logging.getLogger(__name__)

BASE_URL = "https://www2.census.gov/programs-surveys/acs/summary_file"
BLOCK_GROUP = "1500000US"
TRACT = "1400000US"
COUNTY = "0500000US"
CONTROLLED = -555555555  # MOE code: estimate is controlled to an official count
_COL = re.compile(r"^(?P<table>[BC]\d{5}[A-Z]?)_(?P<kind>[EM])(?P<line>\d{3})$")


@dataclass(frozen=True)
class TableFile:
    table: str
    path: Path
    source_url: str
    sha256: str
    block_groups: int
    tracts: int


def table_url(year: int, table: str, base_url: str = BASE_URL) -> str:
    return f"{base_url}/{year}/table-based-SF/data/5YRData/acsdt5y{year}-{table.lower()}.dat"


def file_name(year: int, table: str) -> str:
    return f"acsdt5y{year}-{table.lower()}.dat"


def _check_header(header: str, table: str, source: str) -> None:
    cols = header.rstrip("\r\n").split("|")
    if not cols or cols[0].lstrip("﻿") != "GEO_ID" or len(cols) < 3:
        raise UnknownLayoutError(f"{source}: expected a GEO_ID|{table}_E001|... header")
    for c in cols[1:]:
        m = _COL.match(c)
        if not m or m["table"] != table:
            raise UnknownLayoutError(f"{source}: unexpected column {c!r} for table {table}")


def fetch_table(
    year: int, table: str, county_fips: str, out_dir: Path, base_url: str = BASE_URL
) -> TableFile:
    """Download one national table and write only `county_fips`'s rows to `out_dir`."""
    url = table_url(year, table, base_url)
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / file_name(year, table)
    keep = tuple(f"{p}{county_fips}" for p in (BLOCK_GROUP, TRACT, COUNTY))
    tmp = out.with_suffix(".part")
    with urllib.request.urlopen(url, timeout=120) as resp, tmp.open("w", encoding="utf-8") as f:
        lines = (raw.decode("utf-8") for raw in resp)
        header = next(lines, "")
        _check_header(header, table, url)
        f.write(header.lstrip("﻿"))
        for line in lines:
            if line.startswith(keep):
                f.write(line)
    tmp.replace(out)
    info = describe(out, table, url)
    log.info("fetched %s: %d block groups -> %s", table, info.block_groups, out)
    return info


def describe(path: Path, table: str, source_url: str) -> TableFile:
    data = path.read_bytes()
    lines = data.decode("utf-8").splitlines()
    bgs = sum(1 for line in lines if line.startswith(BLOCK_GROUP))
    tracts = sum(1 for line in lines if line.startswith(TRACT))
    return TableFile(table, path, source_url, hashlib.sha256(data).hexdigest(), bgs, tracts)


@dataclass(frozen=True)
class TableData:
    estimates: pd.DataFrame  # index unit GEOID (block group 12, tract 11), columns = lines
    moes: pd.DataFrame
    county_estimates: pd.Series  # the published county row, by line


def read_table(path: Path, table: str, level: str = "block_group") -> TableData:
    """Estimates and MOEs of one level ('block_group' | 'tract'). Fails on any odd value."""
    with path.open(encoding="utf-8") as f:
        _check_header(f.readline(), table, str(path))
    raw = pd.read_csv(path, sep="|", dtype=str, keep_default_na=False)
    geo = raw.pop("GEO_ID")
    values = raw.apply(pd.to_numeric, errors="coerce")
    if values.isna().any().any():
        bad = values.columns[values.isna().any()].tolist()
        raise UnknownLayoutError(f"{path}: non-numeric values in {bad[:5]}")
    lines = {c: int(c[-3:]) for c in values.columns}
    est = values[[c for c in values.columns if "_E" in c]].rename(columns=lines)
    moe = values[[c for c in values.columns if "_M" in c]].rename(columns=lines)
    moe = moe.mask(moe == CONTROLLED, 0.0)  # controlled estimate: no sampling error
    if (est < 0).any().any() or (moe < 0).any().any():
        raise UnknownLayoutError(f"{path}: negative estimate or unexplained MOE code")
    prefix = BLOCK_GROUP if level == "block_group" else TRACT
    is_unit = geo.str.startswith(prefix)
    county = est[geo.str.startswith(COUNTY)]
    if len(county) != 1:
        raise UnknownLayoutError(f"{path}: expected one county row, found {len(county)}")
    if not is_unit.any():
        raise UnknownLayoutError(f"{path}: no {level} rows")
    index = geo[is_unit].str.removeprefix(prefix)
    return TableData(
        est[is_unit].set_axis(index), moe[is_unit].set_axis(index), county.iloc[0].astype(float)
    )
