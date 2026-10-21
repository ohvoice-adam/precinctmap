-- Materialized results by geography. Rebuilt per election by `precinctmap aggregate run`.
-- An output row (feature x choice) can combine exact and allocated precincts, so it records
-- the exact and allocated parts; the per-precinct split_share lives in geo_contributions.
-- geography 'precinct' is the identity mapping (every row exact).

CREATE TABLE geo_results (
    election_id         VARCHAR NOT NULL,
    contest_id          VARCHAR NOT NULL,
    choice_id           VARCHAR NOT NULL,
    geography           VARCHAR NOT NULL,
    boundary_set_id     VARCHAR NOT NULL,
    feature_id          VARCHAR NOT NULL,
    votes               DOUBLE NOT NULL,         -- allocated parts are fractional
    votes_exact         DOUBLE NOT NULL,
    votes_allocated     DOUBLE NOT NULL,
    precincts_exact     INTEGER NOT NULL,
    precincts_allocated INTEGER NOT NULL,
    method              VARCHAR NOT NULL CHECK (method IN ('exact', 'allocated', 'mixed')),
    PRIMARY KEY (election_id, geography, choice_id, feature_id)
);

CREATE TABLE geo_turnout (
    election_id     VARCHAR NOT NULL,
    geography       VARCHAR NOT NULL,
    boundary_set_id VARCHAR NOT NULL,
    feature_id      VARCHAR NOT NULL,
    party           VARCHAR NOT NULL,
    registered      DOUBLE,
    ballots_cast    DOUBLE,
    ballots_blank   DOUBLE,
    PRIMARY KEY (election_id, geography, feature_id, party)
);

-- Which precincts feed each feature, with what share and method (detail panel, export).
CREATE TABLE geo_contributions (
    election_id     VARCHAR NOT NULL,
    geography       VARCHAR NOT NULL,
    boundary_set_id VARCHAR NOT NULL,
    feature_id      VARCHAR NOT NULL,
    precinct_name   VARCHAR NOT NULL,
    split_share     DOUBLE NOT NULL,
    method          VARCHAR NOT NULL,
    weight_basis    VARCHAR NOT NULL,
    PRIMARY KEY (election_id, geography, feature_id, precinct_name)
);

-- Per choice and geography: source = mapped + excluded + unassigned (rule 4).
CREATE TABLE geo_reconciliation (
    election_id VARCHAR NOT NULL,
    contest_id  VARCHAR NOT NULL,
    choice_id   VARCHAR NOT NULL,
    geography   VARCHAR NOT NULL,
    source      DOUBLE NOT NULL,                 -- Franklin precinct total
    mapped      DOUBLE NOT NULL,
    excluded    DOUBLE NOT NULL,                 -- logged exclusions (e.g. not in Columbus)
    unassigned  DOUBLE NOT NULL,                 -- eligible but outside every unit (logged)
    ok          BOOLEAN NOT NULL,
    PRIMARY KEY (election_id, geography, choice_id)
);
