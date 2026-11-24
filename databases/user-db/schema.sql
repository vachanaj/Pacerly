\connect user_db user_svc;

CREATE TABLE IF NOT EXISTS user_profiles (
    user_id UUID PRIMARY KEY,
    email VARCHAR(255) UNIQUE NOT NULL,
    display_name VARCHAR(120) NOT NULL,
    height_cm NUMERIC(5, 2) CHECK (height_cm IS NULL OR (height_cm > 50 AND height_cm <= 275)),
    weight_kg NUMERIC(5, 2) CHECK (weight_kg IS NULL OR (weight_kg > 20 AND weight_kg <= 350)),
    resting_hr INT CHECK (resting_hr IS NULL OR (resting_hr >= 25 AND resting_hr <= 140)),
    max_hr INT CHECK (max_hr IS NULL OR (max_hr >= 100 AND max_hr <= 240)),
    baseline_pace_sec_per_km INT CHECK (
        baseline_pace_sec_per_km IS NULL OR (baseline_pace_sec_per_km >= 120 AND baseline_pace_sec_per_km <= 1200)
    ),
    weekly_distance_goal_km NUMERIC(6, 2) NOT NULL DEFAULT 30.00 CHECK (weekly_distance_goal_km >= 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_user_profiles_email ON user_profiles (email);

CREATE OR REPLACE FUNCTION set_updated_at_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_user_profiles_updated_at ON user_profiles;
CREATE TRIGGER trg_user_profiles_updated_at
BEFORE UPDATE ON user_profiles
FOR EACH ROW
EXECUTE FUNCTION set_updated_at_timestamp();