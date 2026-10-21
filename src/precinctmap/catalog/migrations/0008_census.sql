-- Census demographics (American Community Survey 5-year estimates) by geography.
-- Block-group estimates are split across 2020 blocks (by population or housing units), and
-- each block counts in the area of every geography that holds its interior point.

CREATE TABLE census_releases (
    release_id  VARCHAR PRIMARY KEY,             -- e.g. 'acs5-2024'
    label       VARCHAR NOT NULL,                -- 'ACS 2020-2024 5-year estimates'
    year_start  INTEGER NOT NULL,
    year_end    INTEGER NOT NULL,
    county      VARCHAR NOT NULL,
    as_of       DATE NOT NULL,                   -- boundary sets valid on this date
    loaded_at   TIMESTAMP NOT NULL DEFAULT current_timestamp
);

-- One filtered summary-file table per row (county rows only; national file never stored).
CREATE TABLE census_files (
    release_id    VARCHAR NOT NULL,
    table_id      VARCHAR NOT NULL,              -- 'B15003'
    filename      VARCHAR NOT NULL,
    source_url    VARCHAR NOT NULL,
    sha256        VARCHAR NOT NULL,              -- of the filtered file as stored
    block_groups  INTEGER NOT NULL,
    PRIMARY KEY (release_id, table_id)
);

-- One row per (geography, feature, metric). `base` is the universe estimate (denominator) the
-- value rests on; `moe` is the 90% margin of error in the value's units.
CREATE TABLE census_stats (
    release_id      VARCHAR NOT NULL,
    geography       VARCHAR NOT NULL,
    boundary_set_id VARCHAR NOT NULL,
    feature_id      VARCHAR NOT NULL,
    metric          VARCHAR NOT NULL,
    value           DOUBLE,
    moe             DOUBLE,
    base            DOUBLE,
    reliable        BOOLEAN NOT NULL,            -- coefficient of variation <= 30%
    PRIMARY KEY (release_id, geography, feature_id, metric)
);

CREATE TABLE census_log (
    release_id VARCHAR NOT NULL,
    issue      VARCHAR NOT NULL,
    detail     VARCHAR NOT NULL
);
