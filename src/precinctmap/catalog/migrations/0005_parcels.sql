-- Auditor parcels located in precincts and Columbus council districts, plus a de-identified
-- address -> precinct table derived from the county voter file (no names, IDs, birth dates,
-- party, vote history, or per-address voter counts are ever stored).

-- Source codes per feature (e.g. BOE PRECINCTID '01082E'), for joins to other BOE files.
CREATE TABLE feature_codes (
    boundary_set_id VARCHAR NOT NULL,
    feature_id      VARCHAR NOT NULL,
    code            VARCHAR NOT NULL,
    PRIMARY KEY (boundary_set_id, code)
);

CREATE TABLE address_files (
    file_id     VARCHAR PRIMARY KEY,             -- sha256
    filename    VARCHAR NOT NULL,
    as_of       DATE NOT NULL,
    rows_read   BIGINT NOT NULL,
    addresses   BIGINT NOT NULL,
    loaded_at   TIMESTAMP NOT NULL DEFAULT current_timestamp,
    status      VARCHAR NOT NULL CHECK (status IN ('active', 'superseded'))
);

-- One row per distinct residential street address (unit numbers dropped).
CREATE TABLE voter_addresses (
    file_id          VARCHAR NOT NULL,
    zip5             VARCHAR NOT NULL,
    house_no         VARCHAR NOT NULL,
    street           VARCHAR NOT NULL,           -- e.g. 'E NORTHWOOD AVE'
    precinct_code    VARCHAR NOT NULL,           -- most common code at the address
    precinct_codes   INTEGER NOT NULL,           -- distinct codes seen (> 1 = split address)
    council_district VARCHAR,                    -- '1'..'9' for Columbus addresses
    city_code        VARCHAR,
    PRIMARY KEY (file_id, zip5, house_no, street)
);

CREATE TABLE parcel_files (
    file_id         VARCHAR PRIMARY KEY,         -- sha256
    filename        VARCHAR NOT NULL,
    stored_path     VARCHAR NOT NULL,
    as_of           DATE NOT NULL,
    adapter         VARCHAR NOT NULL,
    staging_id      VARCHAR NOT NULL,
    parcels         BIGINT NOT NULL,
    address_file_id VARCHAR,                     -- voter-address table used for the cross-check
    ingested_at     TIMESTAMP NOT NULL DEFAULT current_timestamp,
    status          VARCHAR NOT NULL CHECK (status IN ('active', 'superseded'))
);

-- Property attributes and site address. Owner names and mailing addresses are dropped at read.
CREATE TABLE parcels (
    file_id   VARCHAR NOT NULL,
    pid       VARCHAR NOT NULL,                  -- 'DDD-NNNNNN' (tax district - parcel number)
    pclass    VARCHAR,
    landuse   VARCHAR,
    taxdesi   VARCHAR,
    school    VARCHAR,
    site_address VARCHAR,
    house_no  VARCHAR,
    street    VARCHAR,
    city      VARCHAR,
    zip5      VARCHAR,
    acres     DOUBLE,
    appraised_total DOUBLE,
    exempt_total    DOUBLE,
    annual_tax      DOUBLE,
    sale_price      DOUBLE,
    transfer_date   VARCHAR,
    homestead       VARCHAR,
    dwelling        VARCHAR,
    rooms     INTEGER,
    bedrooms  INTEGER,
    year_built VARCHAR,
    attributes JSON NOT NULL,                    -- every other non-owner source column, raw
    x_ft      DOUBLE,                            -- EPSG:3735 (NAD83 Ohio South, US feet); NULL if unusable
    y_ft      DOUBLE,
    PRIMARY KEY (file_id, pid)
);

CREATE TABLE parcel_assignments (
    file_id          VARCHAR NOT NULL,
    pid              VARCHAR NOT NULL,
    precinct_set_id  VARCHAR NOT NULL,
    precinct_name    VARCHAR,
    precinct_method  VARCHAR NOT NULL CHECK (precinct_method IN
        ('point_in_polygon', 'nearest', 'voter_address', 'unassigned')),
    precinct_distance_ft DOUBLE,                 -- for 'nearest'
    council_set_id   VARCHAR,
    council_district VARCHAR,                    -- feature_id of the district
    council_method   VARCHAR NOT NULL CHECK (council_method IN
        ('point_in_polygon', 'voter_address', 'nearest', 'not_in_columbus', 'unassigned')),
    voter_match      BOOLEAN NOT NULL,           -- site address found in the voter-address table
    voter_precinct   VARCHAR,                    -- precinct name per the voter file
    voter_council    VARCHAR,
    precinct_agrees  BOOLEAN,                    -- NULL when there is no voter match
    council_agrees   BOOLEAN,
    PRIMARY KEY (file_id, pid)
);

CREATE TABLE parcel_log (
    file_id VARCHAR NOT NULL,
    pid     VARCHAR,
    issue   VARCHAR NOT NULL,
    detail  VARCHAR NOT NULL
);
