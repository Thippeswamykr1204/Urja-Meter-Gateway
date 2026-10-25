CREATE TABLE meter_conflicts (
    record_id TEXT PRIMARY KEY,
    meter_id TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    quality_json TEXT NOT NULL,
    indexed_at TEXT NOT NULL
);
