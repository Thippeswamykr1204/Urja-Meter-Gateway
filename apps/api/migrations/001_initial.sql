CREATE TABLE meters (
    id TEXT PRIMARY KEY,
    serial_number TEXT,
    name TEXT,
    status TEXT,
    latitude REAL,
    longitude REAL,
    network_node_id TEXT,
    last_seen_at TEXT,
    source_timestamp TEXT,
    quality_json TEXT NOT NULL,
    provenance_json TEXT NOT NULL,
    indexed_at TEXT NOT NULL,
    last_seen_in_source TEXT,
    deleted_at TEXT
);

CREATE VIRTUAL TABLE meters_fts USING fts5(
    id, serial_number, name, content='meters', content_rowid='rowid'
);

CREATE TRIGGER meters_ai AFTER INSERT ON meters BEGIN
  INSERT INTO meters_fts(rowid, id, serial_number, name)
  VALUES (new.rowid, new.id, new.serial_number, new.name);
END;
CREATE TRIGGER meters_ad AFTER DELETE ON meters BEGIN
  INSERT INTO meters_fts(meters_fts, rowid, id, serial_number, name)
  VALUES ('delete', old.rowid, old.id, old.serial_number, old.name);
END;
CREATE TRIGGER meters_au AFTER UPDATE ON meters BEGIN
  INSERT INTO meters_fts(meters_fts, rowid, id, serial_number, name)
  VALUES ('delete', old.rowid, old.id, old.serial_number, old.name);
  INSERT INTO meters_fts(rowid, id, serial_number, name)
  VALUES (new.rowid, new.id, new.serial_number, new.name);
END;

CREATE TABLE readings (
    meter_id TEXT NOT NULL REFERENCES meters(id),
    timestamp TEXT NOT NULL,
    original_timestamp TEXT,
    value REAL,
    unit TEXT,
    original_value REAL,
    original_unit TEXT,
    quality_json TEXT NOT NULL,
    indexed_at TEXT NOT NULL,
    PRIMARY KEY (meter_id, timestamp)
);

CREATE TABLE hierarchy_nodes (
    record_id TEXT PRIMARY KEY,
    node_id TEXT NOT NULL,
    name TEXT,
    node_type TEXT NOT NULL,
    parent_id TEXT,
    meter_count INTEGER NOT NULL,
    consumption_total REAL,
    quality_json TEXT NOT NULL,
    indexed_at TEXT NOT NULL
);

CREATE TABLE sync_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    status TEXT NOT NULL,
    meters_seen INTEGER NOT NULL DEFAULT 0,
    readings_seen INTEGER NOT NULL DEFAULT 0,
    hierarchy_nodes_seen INTEGER NOT NULL DEFAULT 0,
    error TEXT
);

CREATE INDEX readings_meter_timestamp ON readings(meter_id, timestamp);
CREATE INDEX meters_location ON meters(latitude, longitude);
CREATE INDEX meters_status ON meters(status);
