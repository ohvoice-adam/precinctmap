"""Each parcel's area in every geography, as SQL over parcel_assignments."""

# geography -> (set column, feature column) in parcel_assignments
GEOGRAPHY_COLUMNS = {
    "precinct": ("precinct_set_id", "precinct_name"),
    "council_district": ("council_set_id", "council_district"),
    "municipality": ("municipality_set_id", "municipality"),
    "zcta": ("zcta_set_id", "zcta"),
}
GEOGRAPHIES = ("precinct", "council_district", "municipality", "ward", "zcta")

# A parcel's ward is its precinct's ward: the exact precinct -> ward crosswalk of the ward set
# derived from the parcel's precinct set (so a ward can never disagree with the precinct).
_WARD = (
    "SELECT a.file_id, a.pid, x.target_set_id AS boundary_set_id, x.feature_id"
    " FROM parcel_assignments a"
    " JOIN boundary_sets w ON w.geography = 'ward' AND w.derived_from = a.precinct_set_id"
    " JOIN precinct_crosswalk x ON x.precinct_set_id = a.precinct_set_id"
    " AND x.target_set_id = w.boundary_set_id AND x.precinct_name = a.precinct_name"
)


def assigned_sql(geo: str) -> str:
    """Subquery of (file_id, pid, boundary_set_id, feature_id): each parcel's area in `geo`."""
    if geo == "ward":
        return _WARD
    set_col, feat_col = GEOGRAPHY_COLUMNS[geo]
    return (
        f"SELECT file_id, pid, {set_col} AS boundary_set_id, {feat_col} AS feature_id"
        " FROM parcel_assignments"
    )
