ALTER TABLE sync_runs ADD COLUMN duration_seconds REAL;
ALTER TABLE sync_runs ADD COLUMN records_rejected INTEGER NOT NULL DEFAULT 0;
ALTER TABLE sync_runs ADD COLUMN portal_latency_seconds REAL;
ALTER TABLE sync_runs ADD COLUMN checkpoint TEXT;
ALTER TABLE sync_runs ADD COLUMN partial INTEGER NOT NULL DEFAULT 0;
ALTER TABLE readings ADD COLUMN reading_kind TEXT NOT NULL DEFAULT 'unknown';
ALTER TABLE hierarchy_nodes ADD COLUMN consumption_unit TEXT;
ALTER TABLE hierarchy_nodes ADD COLUMN consumption_share REAL;
ALTER TABLE hierarchy_nodes ADD COLUMN missing_reading_count INTEGER NOT NULL DEFAULT 0;
ALTER TABLE hierarchy_nodes ADD COLUMN mixed_units INTEGER NOT NULL DEFAULT 0;

CREATE TABLE dataset_status (
    data_type TEXT PRIMARY KEY,
    status TEXT NOT NULL,
    source TEXT NOT NULL,
    fetched_at TEXT,
    indexed_at TEXT,
    portal_timestamp TEXT,
    stale INTEGER NOT NULL DEFAULT 0,
    partial INTEGER NOT NULL DEFAULT 0,
    records_seen INTEGER NOT NULL DEFAULT 0,
    records_rejected INTEGER NOT NULL DEFAULT 0,
    error TEXT
);

CREATE TABLE coverage_ranges (
    meter_id TEXT NOT NULL REFERENCES meters(id),
    start_date TEXT NOT NULL,
    end_date TEXT NOT NULL,
    status TEXT NOT NULL,
    fetched_at TEXT NOT NULL,
    PRIMARY KEY (meter_id, start_date, end_date)
);

CREATE TABLE sync_checkpoints (
    name TEXT PRIMARY KEY,
    position TEXT,
    updated_at TEXT NOT NULL
);

CREATE TABLE reading_conflicts (
    conflict_id TEXT PRIMARY KEY,
    meter_id TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    previous_json TEXT NOT NULL,
    incoming_json TEXT NOT NULL,
    indexed_at TEXT NOT NULL
);

CREATE TABLE sync_snapshot_records (
    run_id INTEGER NOT NULL REFERENCES sync_runs(id),
    data_type TEXT NOT NULL,
    record_key TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    PRIMARY KEY (run_id, data_type, record_key)
);

CREATE INDEX coverage_ranges_lookup ON coverage_ranges(meter_id, start_date, end_date);
CREATE INDEX reading_conflicts_lookup ON reading_conflicts(meter_id, timestamp);
