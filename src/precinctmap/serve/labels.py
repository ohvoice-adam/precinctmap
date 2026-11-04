"""User-facing wording shared by the API payloads (sentence case, plain language)."""

GEOGRAPHY_LABELS = {
    "precinct": "Precinct",
    "council_district": "Columbus council district",
    "municipality": "City, village, or township",
    "ward": "Ward",
    "zcta": "ZIP code area (ZCTA)",
    "state_house": "Ohio House district",
    "state_senate": "Ohio Senate district",
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

STATE_DISTRICTS = ("state_house", "state_senate")
STATE_DISTRICT_NOTE = (
    "Only the Franklin County part of each district is shown, so district totals are Franklin"
    " County votes, not the whole district's. Where a precinct is split between districts, its"
    " votes are allocated by 2020 census block population."
)
RETROACTIVE_STATE_DISTRICTS = (
    "Legislative districts are drawn on a different map than the one this election was held"
    " under; the closest available map is applied."
)

PARCEL_DISTRICT_NOTE = (
    "Only the Franklin County part of each district is shown. Each parcel is placed in the"
    " district that holds its point on the county auditor's map, using the legislative map in"
    " effect on the parcel file's date."
)
CENSUS_DISTRICT_NOTE = (
    "Only the Franklin County part of each district is shown. Each census block counts in the"
    " district that holds its center point, using the legislative map in effect on the release's"
    " placement date."
)
GEOGRAPHY_ORDER = (
    "precinct",
    "council_district",
    "municipality",
    "ward",
    "zcta",
    "state_house",
    "state_senate",
)
