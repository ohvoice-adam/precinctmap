-- Residential property statistics by geography.
-- Rental flags are derived at read from owner name / owner address; the names and addresses
-- themselves are never stored (only the booleans).

ALTER TABLE parcels ADD COLUMN building_value DOUBLE;          -- APPRBLD
ALTER TABLE parcels ADD COLUMN grade VARCHAR;                  -- GRADE, e.g. 'C+1'
ALTER TABLE parcels ADD COLUMN grade_score DOUBLE;             -- A=5 .. E=1, +-0.2 per step
ALTER TABLE parcels ADD COLUMN condition VARCHAR;              -- COND (blank in the 2026 file)
ALTER TABLE parcels ADD COLUMN residential BOOLEAN;            -- PCLASS R with a dwelling
ALTER TABLE parcels ADD COLUMN owner_llc BOOLEAN;              -- 'LLC' in NAME1-3
ALTER TABLE parcels ADD COLUMN owner_address_differs BOOLEAN;  -- NULL when no owner address
ALTER TABLE parcels ADD COLUMN likely_rental BOOLEAN;

ALTER TABLE parcel_assignments ADD COLUMN municipality_set_id VARCHAR;
ALTER TABLE parcel_assignments ADD COLUMN municipality VARCHAR;
ALTER TABLE parcel_assignments ADD COLUMN municipality_method VARCHAR;
ALTER TABLE parcel_assignments ADD COLUMN zcta_set_id VARCHAR;
ALTER TABLE parcel_assignments ADD COLUMN zcta VARCHAR;
ALTER TABLE parcel_assignments ADD COLUMN zcta_method VARCHAR;

-- One row per (geography, feature, metric). `n` = residential parcels behind the value.
CREATE TABLE parcel_stats (
    file_id         VARCHAR NOT NULL,
    geography       VARCHAR NOT NULL,
    boundary_set_id VARCHAR NOT NULL,
    feature_id      VARCHAR NOT NULL,
    metric          VARCHAR NOT NULL,
    value           DOUBLE,
    n               BIGINT NOT NULL,
    PRIMARY KEY (file_id, geography, feature_id, metric)
);
