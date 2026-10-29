PRAGMA foreign_keys = ON;

-- Login accounts. One account can own one test-subject profile (see users.account_id below).
CREATE TABLE IF NOT EXISTS accounts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    recovery_hash TEXT NOT NULL,
    failed_attempts INTEGER DEFAULT 0,
    lockout_until REAL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS auth_tokens (
    token TEXT PRIMARY KEY,
    account_id INTEGER NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    expires_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS consent_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id INTEGER NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    agreed_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Test-subject profile. account_id links it to the login that owns it.
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id INTEGER REFERENCES accounts(id) ON DELETE CASCADE,
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
    model_probability REAL,
    stage_score REAL,
    change_index REAL,
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
    velocity_cv REAL, jerk_rms REAL, path_deviation REAL, guide_deviation REAL,
    stage_score REAL,
    change_index REAL,
    compared_step INTEGER,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (session_id, step)
);

CREATE TABLE IF NOT EXISTS raw_signals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    movement_result_id INTEGER NOT NULL REFERENCES movement_results(id) ON DELETE CASCADE,
    data_gz BLOB NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_users_account ON users(account_id);