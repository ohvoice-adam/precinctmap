"""User-facing wording shared by the API payloads (sentence case, plain language)."""

GEOGRAPHY_LABELS = {
    "precinct": "Precinct",
    "council_district": "Columbus council district",
    "municipality": "City, village, or township",
    "ward": "Ward",
    "zcta": "ZIP code area (ZCTA)",
    "county": "County",
}

RETROACTIVE_PRECINCTS = (
    "Precinct boundaries are from July 2025 and are applied to this earlier election."
)
RETROACTIVE_COUNCIL = (
    "Columbus council districts were first used in 2023; their boundaries are applied to this"
    " earlier election."
)
FRANKLIN_ONLY = "Franklin County results only."
NOT_IN_COLUMBUS = "Precincts outside Columbus are not part of any council district."
ZCTA_NOTE = (
    "ZIP code areas are Census ZCTAs, which approximate USPS ZIP codes. "
    "Only the Franklin County part of each area is shown."
)
