-- Allow 'reprocess' events: re-deriving an already-ingested file after a correction-table or
-- adapter change. DuckDB cannot alter a CHECK constraint, so rebuild the table.

CREATE TABLE ingest_events_v2 (
    occurred_at TIMESTAMP NOT NULL DEFAULT current_timestamp,
    staging_id  VARCHAR NOT NULL,
    action      VARCHAR NOT NULL CHECK (action IN ('commit', 'noop', 'supersede', 'reprocess')),
    election_id VARCHAR,
    file_id     VARCHAR,
    detail      VARCHAR NOT NULL
);
INSERT INTO ingest_events_v2 SELECT * FROM ingest_events;
DROP TABLE ingest_events;
ALTER TABLE ingest_events_v2 RENAME TO ingest_events;
