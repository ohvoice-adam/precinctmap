-- State legislative districts (Ohio House and Senate). DuckDB cannot alter a CHECK constraint,
-- so rebuild boundary_sets to allow 'state_house' and 'state_senate'.

CREATE TABLE boundary_sets_v3 (
    boundary_set_id VARCHAR PRIMARY KEY,
    geography       VARCHAR NOT NULL CHECK (geography IN
        ('precinct', 'council_district', 'municipality', 'ward', 'zcta', 'state_house',
         'state_senate', 'county')),
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
INSERT INTO boundary_sets_v3 BY NAME SELECT * FROM boundary_sets;
DROP TABLE boundary_sets;
ALTER TABLE boundary_sets_v3 RENAME TO boundary_sets;
