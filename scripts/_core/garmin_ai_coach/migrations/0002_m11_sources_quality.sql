ALTER TABLE activity ADD COLUMN speed_m_per_s REAL;

CREATE TABLE source_record (
    id INTEGER PRIMARY KEY,
    source_kind TEXT NOT NULL,
    region TEXT NOT NULL,
    record_key TEXT NOT NULL,
    file_sha256 TEXT NOT NULL,
    file_line INTEGER NOT NULL,
    source_label TEXT NOT NULL,
    parser_version TEXT NOT NULL,
    distance_rule_version TEXT NOT NULL,
    timezone_setting TEXT NOT NULL,
    distance_unit TEXT NOT NULL,
    raw_fields_json TEXT NOT NULL,
    normalized_json TEXT NOT NULL,
    batch_id INTEGER NOT NULL REFERENCES import_batch(id),
    activity_id INTEGER REFERENCES activity(id),
    status TEXT NOT NULL,
    reason TEXT NOT NULL,
    created_at_utc TEXT NOT NULL,
    UNIQUE(source_kind,region,record_key)
);
CREATE INDEX source_record_activity_idx ON source_record(activity_id);

CREATE TABLE source_candidate (
    source_record_id INTEGER NOT NULL REFERENCES source_record(id),
    activity_id INTEGER NOT NULL REFERENCES activity(id),
    time_gap_s REAL NOT NULL,
    distance_gap_m REAL,
    timer_gap_s REAL,
    evidence_json TEXT NOT NULL,
    decision TEXT NOT NULL,
    PRIMARY KEY(source_record_id,activity_id)
);

CREATE TABLE activity_metric_quality (
    activity_id INTEGER NOT NULL REFERENCES activity(id),
    metric TEXT NOT NULL,
    status TEXT NOT NULL,
    reason TEXT NOT NULL,
    policy_version TEXT NOT NULL,
    PRIMARY KEY(activity_id,metric)
);
