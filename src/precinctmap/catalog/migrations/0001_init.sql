-- Catalog, results, precinct boundaries. Long format throughout.
-- Precinct key: (county, precinct_name, election_date) via elections; precinct_name is the
-- normalized name (ward padded). PRECINCT CODE is a row ordinal and is kept for tracing only.
-- No FOREIGN KEY clauses: DuckDB rejects updates to referenced rows, and supersede logic
-- needs them. Referential integrity is enforced in precinctmap.ingest.commit and its tests.

CREATE TABLE elections (
    election_id   VARCHAR PRIMARY KEY,           -- franklin-2024-11-05-general
    county        VARCHAR NOT NULL,
    election_date DATE NOT NULL,
    election_type VARCHAR NOT NULL CHECK (election_type IN ('primary', 'general', 'special')),
    label         VARCHAR NOT NULL,
    certified     BOOLEAN NOT NULL,
    UNIQUE (county, election_date, election_type)
);

CREATE TABLE source_files (
    file_id         VARCHAR PRIMARY KEY,         -- sha256 of the file bytes
    election_id     VARCHAR NOT NULL,
    filename        VARCHAR NOT NULL,
    sha256          VARCHAR NOT NULL UNIQUE,
    stored_path     VARCHAR NOT NULL,            -- copy under data/raw/
    adapter         VARCHAR NOT NULL,
    adapter_version VARCHAR NOT NULL,
    staging_id      VARCHAR NOT NULL,
    ingested_at     TIMESTAMP NOT NULL,
    row_count       INTEGER NOT NULL,            -- precinct rows (excl. pseudo and total rows)
    status          VARCHAR NOT NULL CHECK (status IN ('active', 'superseded')),
    superseded_by   VARCHAR
);

CREATE TABLE contests (
    contest_id      VARCHAR PRIMARY KEY,         -- <election_id>:<party|np>:<slug>
    election_id     VARCHAR NOT NULL,
    file_id         VARCHAR NOT NULL,
    source_ordinal  INTEGER NOT NULL,
    name_raw        VARCHAR NOT NULL,
    name_display    VARCHAR NOT NULL,
    contest_type    VARCHAR NOT NULL CHECK (contest_type IN ('candidate', 'issue')),
    party           VARCHAR,                     -- primary ballot party; NULL = nonpartisan/general
    jurisdiction    VARCHAR,
    vote_for        INTEGER,
    vote_for_source VARCHAR NOT NULL CHECK (vote_for_source IN ('inferred', 'manual', 'unknown'))
);

CREATE TABLE choices (
    choice_id      VARCHAR PRIMARY KEY,          -- <contest_id>:<slug>
    contest_id     VARCHAR NOT NULL,
    source_ordinal INTEGER NOT NULL,
    source_column  INTEGER NOT NULL,             -- 1-based sheet column
    name_raw       VARCHAR NOT NULL,
    name_display   VARCHAR NOT NULL,
    party          VARCHAR,
    choice_kind    VARCHAR NOT NULL CHECK (choice_kind IN
        ('candidate', 'yes', 'no', 'write_in', 'withdrawn', 'no_petition', 'over', 'under')),
    file_id        VARCHAR NOT NULL
);

-- One row per precinct per choice, only where the contest was on that precinct's ballot.
CREATE TABLE precinct_results (
    election_id   VARCHAR NOT NULL,
    precinct_name VARCHAR NOT NULL,
    contest_id    VARCHAR NOT NULL,
    choice_id     VARCHAR NOT NULL,
    votes         BIGINT NOT NULL CHECK (votes >= 0),
    file_id       VARCHAR NOT NULL,
    PRIMARY KEY (election_id, precinct_name, choice_id)
);

CREATE TABLE precinct_sources (
    election_id       VARCHAR NOT NULL,
    precinct_name     VARCHAR NOT NULL,
    precinct_name_raw VARCHAR NOT NULL,
    precinct_code_raw VARCHAR NOT NULL,
    source_row        INTEGER NOT NULL,
    file_id           VARCHAR NOT NULL,
    PRIMARY KEY (election_id, precinct_name)
);

CREATE TABLE precinct_turnout (
    election_id   VARCHAR NOT NULL,
    precinct_name VARCHAR NOT NULL,
    party         VARCHAR NOT NULL,              -- 'ALL' or a party code
    registered    BIGINT,
    ballots_cast  BIGINT,
    ballots_blank BIGINT,
    file_id       VARCHAR NOT NULL,
    PRIMARY KEY (election_id, precinct_name, party)
);

-- Other counties' share of joint contests, from the export's pseudo-rows. Never mapped.
CREATE TABLE out_of_county_results (
    election_id VARCHAR NOT NULL,
    county_name VARCHAR NOT NULL,
    contest_id  VARCHAR NOT NULL,
    choice_id   VARCHAR NOT NULL,
    votes       BIGINT NOT NULL CHECK (votes >= 0),
    file_id     VARCHAR NOT NULL,
    PRIMARY KEY (election_id, county_name, choice_id)
);

CREATE TABLE normalization_log (
    file_id  VARCHAR NOT NULL,
    kind     VARCHAR NOT NULL,
    location VARCHAR NOT NULL,
    before   VARCHAR NOT NULL,
    after    VARCHAR NOT NULL
);

CREATE TABLE unmatched_precincts (
    file_id         VARCHAR NOT NULL,
    election_id     VARCHAR NOT NULL,
    boundary_set_id VARCHAR NOT NULL,
    precinct_name   VARCHAR NOT NULL,
    side            VARCHAR NOT NULL CHECK (side IN ('results_only', 'boundary_only'))
);

CREATE TABLE ingest_events (
    occurred_at TIMESTAMP NOT NULL DEFAULT current_timestamp,
    staging_id  VARCHAR NOT NULL,
    action      VARCHAR NOT NULL CHECK (action IN ('commit', 'noop', 'supersede')),
    election_id VARCHAR,
    file_id     VARCHAR,
    detail      VARCHAR NOT NULL
);

-- valid_from/valid_to: dates this set is used for (valid_to exclusive, NULL = open).
-- native_from: date the set actually took effect; lookups before it are retroactive.
CREATE TABLE boundary_sets (
    boundary_set_id VARCHAR PRIMARY KEY,
    geography       VARCHAR NOT NULL CHECK (geography IN
        ('precinct', 'council_district', 'municipality', 'zcta', 'county')),
    county          VARCHAR NOT NULL,
    valid_from      DATE NOT NULL,
    valid_to        DATE,
    native_from     DATE,
    source          VARCHAR NOT NULL,
    source_sha256   VARCHAR NOT NULL,
    loaded_at       TIMESTAMP NOT NULL DEFAULT current_timestamp,
    notes           VARCHAR
);

CREATE TABLE features (
    boundary_set_id VARCHAR NOT NULL,
    feature_id      VARCHAR NOT NULL,
    name            VARCHAR NOT NULL,
    jurisdiction    VARCHAR,
    geom            GEOMETRY NOT NULL,           -- EPSG:4269
    PRIMARY KEY (boundary_set_id, feature_id)
);

CREATE TABLE geometry_repairs (
    boundary_set_id VARCHAR NOT NULL,
    feature_id      VARCHAR NOT NULL,
    issue           VARCHAR NOT NULL,
    fix             VARCHAR NOT NULL
);
