-- Boundary registry: derivation lineage, census blocks (allocation weights), and the
-- precinct -> target-unit crosswalks that Phase 4 aggregates through.

ALTER TABLE boundary_sets ADD COLUMN derived_from VARCHAR;

CREATE TABLE census_blocks (
    geoid   VARCHAR PRIMARY KEY,
    vintage INTEGER NOT NULL,
    county  VARCHAR NOT NULL,
    pop     BIGINT NOT NULL,
    housing BIGINT NOT NULL,
    geom    GEOMETRY NOT NULL                    -- EPSG:4269
);

-- One row per (precinct, target unit) piece. split_share is the fraction of the precinct's
-- votes assigned to the unit; it sums to 1 per precinct (excluded precincts have no rows).
CREATE TABLE precinct_crosswalk (
    precinct_set_id VARCHAR NOT NULL,
    target_set_id   VARCHAR NOT NULL,
    precinct_name   VARCHAR NOT NULL,
    feature_id      VARCHAR NOT NULL,
    pop_share       DOUBLE,                      -- share of precinct block population (raw)
    area_share      DOUBLE NOT NULL,             -- share of precinct area (raw)
    split_share     DOUBLE NOT NULL CHECK (split_share > 0 AND split_share <= 1),
    method          VARCHAR NOT NULL CHECK (method IN ('exact', 'allocated')),
    weight_basis    VARCHAR NOT NULL CHECK (weight_basis IN ('jurisdiction', 'population', 'area')),
    PRIMARY KEY (precinct_set_id, target_set_id, precinct_name, feature_id)
);

-- Exclusions, residuals renormalized away, zero-population fallbacks, sliver drops.
CREATE TABLE crosswalk_log (
    precinct_set_id VARCHAR NOT NULL,
    target_set_id   VARCHAR NOT NULL,
    precinct_name   VARCHAR NOT NULL,
    issue           VARCHAR NOT NULL,
    detail          VARCHAR NOT NULL
);
