"""Derived parcel fields: residential status, apartments, housing units, likely rental, grade.

Residential = auditor class R with a dwelling, plus apartment buildings, which the auditor
classes commercial (C) with land use 401 (4-19 units), 402 (20-39) or 403 (40+). Apartment
buildings count as rentals. Units: 1 per class R parcel (condo units are their own parcels),
2 for two-family (520) and 3 for three-family (530); apartments are estimated later from
census blocks and voter-file unit numbers (see parcels/units.py).

Computed while the owner columns are still in memory; only the resulting booleans and scores
are kept (owner names and addresses are dropped right after).

Likely rental = owner name contains 'LLC', or the owner's address differs from the parcel's
site address (house number or ZIP). The owner address is OWNER_ADD1/OWNER_ADD2, not the
tax-bill mailing address (MAILAD*), which in this file is often a mortgage tax-service
PO box: comparing MAILAD flagged 30% of homestead (owner-occupied) parcels; OWNER_ADD flags
~6% once missing owner addresses are treated as unknown.
"""

import re

import pandas as pd

LLC = re.compile(r"\bL\.?\s?L\.?\s?C\b\.?")
_ZIP = re.compile(r"(\d{5})(?:\s*-?\s*\d{4})?\s*$")
_NUM = re.compile(r"^\s*(\d+)")
_GRADE = re.compile(r"^([A-E])(?:([+-])([12]))?$")
GRADE_BASE = {"A": 5.0, "B": 4.0, "C": 3.0, "D": 2.0, "E": 1.0}
GRADE_STEP = 0.2  # C+2 = 3.4 < B-2 = 3.6, so the scale stays monotone
APARTMENT_LAND_USE = {"401": (4, 19), "402": (20, 39), "403": (40, None)}  # unit bounds
MULTI_FAMILY_UNITS = {"520": 2, "530": 3}


def grade_score(grade: str) -> float | None:
    """'C+1' -> 3.2, 'B-2' -> 3.6, 'A' -> 5.0; anything else (blank, unknown) -> None."""
    m = _GRADE.match((grade or "").strip().upper())
    if not m:
        return None
    base, sign, step = m.groups()
    offset = int(step) * GRADE_STEP if step else 0.0
    return GRADE_BASE[base] + (offset if sign == "+" else -offset)


def _house_number(s: pd.Series) -> pd.Series:
    return s.fillna("").str.extract(_NUM)[0]


def owner_address_differs(raw: pd.DataFrame) -> pd.Series:
    """True/False when the owner address is present; None (unknown) when it is blank."""
    owner_no = _house_number(raw["OWNER_ADD1"])
    owner_zip = raw["OWNER_ADD2"].fillna("").str.extract(_ZIP)[0]
    site_no = _house_number(raw["STADDR"])
    site_zip = raw["ZIPCODE"].fillna("").str.strip().str[:5]
    known = raw["OWNER_ADD1"].fillna("").str.strip().ne("")
    differs = (owner_no != site_no) | (owner_zip.fillna(site_zip) != site_zip)
    return differs.astype("boolean").where(known, pd.NA)


def derive(raw: pd.DataFrame) -> pd.DataFrame:
    """residential, owner_llc, owner_address_differs, likely_rental, grade_score per row."""
    names = raw[["NAME1", "NAME2", "NAME3"]].fillna("").agg(" ".join, axis=1).str.upper()
    llc = names.str.contains(LLC)
    differs = owner_address_differs(raw)
    pclass, land_use = raw["PCLASS"].str.strip(), raw["LANDUSE"].str.strip()
    home = pclass.eq("R") & raw["DWELTYP"].str.strip().eq("1")
    apartment = pclass.eq("C") & land_use.isin(list(APARTMENT_LAND_USE))
    units = land_use.map(MULTI_FAMILY_UNITS).fillna(1.0).where(home)
    return pd.DataFrame(
        {
            "residential": home | apartment,
            "apartment": apartment,
            "owner_llc": llc,
            "owner_address_differs": differs,
            "likely_rental": llc | differs.fillna(False).astype(bool) | apartment,
            "grade_score": raw["GRADE"].map(grade_score).where(home),
            "units_estimate": units,
            "units_method": pd.Series("land_use", index=raw.index).where(home),
        },
        index=raw.index,
    )
