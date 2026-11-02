-- Land area of every feature: its own polygon (EPSG:3735) minus TIGER area water, in square
-- miles. Built by `precinctmap boundaries load` (registry/land.py); the divisor for registered
-- voters per square mile. water_sha256 is the area-water file it was cut with.
CREATE TABLE area_land (
    boundary_set_id VARCHAR NOT NULL,
    feature_id      VARCHAR NOT NULL,
    area_sqmi       DOUBLE NOT NULL,
    water_sqmi      DOUBLE NOT NULL,
    land_sqmi       DOUBLE NOT NULL,
    water_sha256    VARCHAR NOT NULL,
    PRIMARY KEY (boundary_set_id, feature_id)
);

-- Which election's registered voters the active parcel file's voter measures use (the most
-- recent election with registration; refreshed after each election commit).
CREATE TABLE parcel_registration (
    file_id      VARCHAR PRIMARY KEY,
    election_id  VARCHAR NOT NULL,
    refreshed_at TIMESTAMP NOT NULL DEFAULT current_timestamp
);
