CREATE TABLE schema_migration (
    version INTEGER PRIMARY KEY,
    applied_at_utc TEXT NOT NULL
);

CREATE TABLE activity (
    id INTEGER PRIMARY KEY,
    provider TEXT NOT NULL,
    region TEXT NOT NULL,
    provider_activity_id TEXT NOT NULL,
    kind TEXT NOT NULL,
    type_key TEXT,
    started_at_raw TEXT,
    started_at_utc TEXT,
    started_at_local TEXT,
    local_date TEXT,
    timezone_basis TEXT NOT NULL,
    distance_m REAL,
    timer_s REAL,
    moving_s REAL,
    elapsed_s REAL,
    pace_s_per_km REAL,
    avg_hr_bpm REAL,
    max_hr_bpm REAL,
    avg_power_w REAL,
    avg_cadence_spm REAL,
    lap_status TEXT NOT NULL DEFAULT 'not_fetched',
    count_status TEXT NOT NULL DEFAULT 'counted',
    revision INTEGER NOT NULL DEFAULT 1,
    first_seen_at_utc TEXT NOT NULL,
    updated_at_utc TEXT NOT NULL,
    UNIQUE (provider, region, provider_activity_id)
);
CREATE INDEX activity_local_date_idx ON activity(local_date, kind);
CREATE INDEX activity_utc_idx ON activity(started_at_utc);

CREATE TABLE activity_source (
    id INTEGER PRIMARY KEY,
    activity_id INTEGER NOT NULL REFERENCES activity(id),
    source_kind TEXT NOT NULL,
    region TEXT NOT NULL,
    source_key TEXT NOT NULL,
    file_sha256 TEXT,
    file_line INTEGER,
    source_label TEXT,
    imported_at_utc TEXT NOT NULL,
    UNIQUE (source_kind, region, source_key)
);
CREATE INDEX activity_source_activity_idx ON activity_source(activity_id);

CREATE TABLE activity_lap (
    id INTEGER PRIMARY KEY,
    activity_id INTEGER NOT NULL REFERENCES activity(id),
    lap_no INTEGER NOT NULL,
    lap_type TEXT,
    distance_m REAL,
    timer_s REAL,
    moving_s REAL,
    elapsed_s REAL,
    avg_hr_bpm REAL,
    max_hr_bpm REAL,
    avg_power_w REAL,
    avg_cadence_spm REAL,
    source_kind TEXT NOT NULL,
    verified_at_utc TEXT NOT NULL,
    UNIQUE (activity_id, lap_no, source_kind)
);

CREATE TABLE import_batch (
    id INTEGER PRIMARY KEY,
    kind TEXT NOT NULL,
    label TEXT NOT NULL,
    file_sha256 TEXT,
    started_at_utc TEXT NOT NULL,
    ended_at_utc TEXT,
    status TEXT NOT NULL,
    records_seen INTEGER NOT NULL DEFAULT 0,
    inserted INTEGER NOT NULL DEFAULT 0,
    updated INTEGER NOT NULL DEFAULT 0,
    linked INTEGER NOT NULL DEFAULT 0,
    unchanged INTEGER NOT NULL DEFAULT 0,
    held_for_review INTEGER NOT NULL DEFAULT 0,
    failed INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE sync_progress (
    id INTEGER PRIMARY KEY,
    mode TEXT NOT NULL,
    range_start TEXT NOT NULL,
    range_end TEXT NOT NULL,
    next_offset INTEGER NOT NULL DEFAULT 0,
    anchor_activity_id TEXT,
    completed INTEGER NOT NULL DEFAULT 0,
    last_attempt_at_utc TEXT,
    last_success_at_utc TEXT,
    last_error_type TEXT,
    UNIQUE (mode, range_start, range_end)
);

CREATE TABLE data_quality_issue (
    id INTEGER PRIMARY KEY,
    activity_id INTEGER REFERENCES activity(id),
    source_id INTEGER REFERENCES activity_source(id),
    code TEXT NOT NULL,
    severity TEXT NOT NULL,
    note TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'open',
    created_at_utc TEXT NOT NULL,
    resolved_at_utc TEXT,
    UNIQUE (activity_id, source_id, code, note)
);
