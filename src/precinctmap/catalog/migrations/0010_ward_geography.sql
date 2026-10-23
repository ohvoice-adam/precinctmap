-- Wards: precincts dissolved by name prefix ('COLUMBUS 01-A', 'COLUMBUS 01-B' -> Columbus
-- Ward 01). DuckDB cannot alter a CHECK constraint, so rebuild boundary_sets to allow 'ward'.

CREATE TABLE boundary_sets_v2 (
    boundary_set_id VARCHAR PRIMARY KEY,
    geography       VARCHAR NOT NULL CHECK (geography IN
        ('precinct', 'council_district', 'municipality', 'ward', 'zcta', 'county')),
    county          VARCHAR NOT NULL,
    valid_from      DATE NOT NULL,
    valid_to        DATE,
    native_from     DATE,
    source          VARCHAR NOT NULL,
    source_sha256   VARCHAR NOT NULL,
    loaded_at       TIMESTAMP NOT NULL DEFAULT current_timestamp,
    notes           VARCHAR,
    derived_from    VARCHAR
);
INSERT INTO boundary_sets_v2 BY NAME SELECT * FROM boundary_sets;
DROP TABLE boundary_sets;
ALTER TABLE boundary_sets_v2 RENAME TO boundary_sets;
