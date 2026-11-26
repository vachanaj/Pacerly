CREATE TABLE IF NOT EXISTS fatigue_activity_ledger (
    activity_id UUID PRIMARY KEY,
    user_id UUID NOT NULL,
    distance_km NUMERIC NOT NULL,
    duration_sec INT NOT NULL,
    avg_pace_sec_per_km INT NOT NULL,
    training_load_score NUMERIC NOT NULL,
    activity_date TIMESTAMPTZ NOT NULL,
    processed_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_fatigue_ledger_user_date
    ON fatigue_activity_ledger (user_id, activity_date DESC);

CREATE TABLE IF NOT EXISTS adaptive_pace_profiles (
    user_id UUID PRIMARY KEY,
    rolling_7d_distance_km NUMERIC NOT NULL DEFAULT 0,
    rolling_7d_fatigue_score NUMERIC NOT NULL DEFAULT 0,
    fatigue_state VARCHAR NOT NULL DEFAULT 'fresh',
    pace_adjustment_factor NUMERIC NOT NULL DEFAULT 1.00,
    target_easy_pace_sec INT NOT NULL,
    target_tempo_pace_sec INT NOT NULL,
    target_interval_pace_sec INT NOT NULL,
    target_long_run_pace_sec INT NOT NULL,
    last_recalculated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);