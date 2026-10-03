PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    age INTEGER NOT NULL,
    gender TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- One session = one full 8-step assessment.
CREATE TABLE IF NOT EXISTS sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    device TEXT NOT NULL DEFAULT 'mouse',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    completed_at TEXT,
    verdict_code TEXT
);

-- Steps 1-4 (steps 1-3 = baseline, step 4 = detection). Audio itself is never stored.
CREATE TABLE IF NOT EXISTS voice_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    step INTEGER NOT NULL,
    f0_mean REAL, jitter_local REAL, jitter_rap REAL, jitter_ppq5 REAL, jitter_ddp REAL,
    shimmer_local REAL, shimmer_db REAL, shimmer_apq3 REAL, shimmer_apq5 REAL, shimmer_dda REAL,
    hnr REAL,
    model_probability REAL,   -- reference only, not used in the verdict
    stage_score REAL,         -- 0-100 irregularity vs reference thresholds
    change_index REAL,        -- 0-100 change vs own baseline (step 4 only)
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (session_id, step)
);

-- Steps 5-8 (5 spiral, 6 wave, 7 free shape = baselines, 8 = detection).
CREATE TABLE IF NOT EXISTS movement_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    step INTEGER NOT NULL,
    task_type TEXT NOT NULL,
    duration_s REAL, n_samples INTEGER, sample_rate_hz REAL,
    tremor_power_4_6 REAL, tremor_power_6_12 REAL, tremor_share REAL, peak_freq_hz REAL,
    velocity_cv REAL, jerk_rms REAL, path_deviation REAL,
    stage_score REAL,
    change_index REAL,        -- step 8 only
    compared_step INTEGER,    -- step 8 only: which baseline step it is compared with
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (session_id, step)
);

CREATE TABLE IF NOT EXISTS raw_signals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    movement_result_id INTEGER NOT NULL REFERENCES movement_results(id) ON DELETE CASCADE,
    data_gz BLOB NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id);