-- Housing-unit estimates, apartment buildings, and voter-file precinct overrides.

-- Distinct unit numbers (RES APT) with at least one registered voter at the address.
-- An address attribute; no voter counts are stored.
ALTER TABLE voter_addresses ADD COLUMN units_with_voters INTEGER;

ALTER TABLE parcels ADD COLUMN apartment BOOLEAN;        -- PCLASS C, land use 401-403
ALTER TABLE parcels ADD COLUMN units_estimate DOUBLE;
ALTER TABLE parcels ADD COLUMN units_method VARCHAR;     -- land_use | voter_units | class_bound | class_median

-- Where the voter file names a different precinct, it wins; the geometry result is kept here.
ALTER TABLE parcel_assignments ADD COLUMN geometry_precinct VARCHAR;
ALTER TABLE parcel_assignments ADD COLUMN geometry_council VARCHAR;
