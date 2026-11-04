-- Parcels placed in Ohio House and Senate districts (point-in-polygon on the auditor's point,
-- using the maps valid on the parcel file's as-of date). Same shape as municipality / zcta.

ALTER TABLE parcel_assignments ADD COLUMN state_house_set_id VARCHAR;
ALTER TABLE parcel_assignments ADD COLUMN state_house VARCHAR;
ALTER TABLE parcel_assignments ADD COLUMN state_house_method VARCHAR;
ALTER TABLE parcel_assignments ADD COLUMN state_senate_set_id VARCHAR;
ALTER TABLE parcel_assignments ADD COLUMN state_senate VARCHAR;
ALTER TABLE parcel_assignments ADD COLUMN state_senate_method VARCHAR;
