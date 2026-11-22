CREATE TABLE IF NOT EXISTS activities (
    activity_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL,
    shoe_id UUID NULL,
    title VARCHAR(255) NOT NULL,
    workout_type VARCHAR(50) NOT NULL,
    total_distance_km NUMERIC(8, 2) NOT NULL CHECK (total_distance_km > 0),
    total_duration_sec INT NOT NULL CHECK (total_duration_sec > 0),
    avg_pace_sec_per_km INT NOT NULL CHECK (avg_pace_sec_per_km > 0),
    perceived_exertion INT CHECK (perceived_exertion BETWEEN 1 AND 10),
    started_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS activity_splits (
    split_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    activity_id UUID NOT NULL REFERENCES activities(activity_id) ON DELETE CASCADE,
    split_number INT NOT NULL CHECK (split_number > 0),
    distance_km NUMERIC(8, 2) NOT NULL CHECK (distance_km > 0),
    duration_sec INT NOT NULL CHECK (duration_sec > 0),
    pace_sec_per_km INT NOT NULL CHECK (pace_sec_per_km > 0),
    elevation_gain_m NUMERIC(8, 2) DEFAULT 0
);

CREATE TABLE IF NOT EXISTS outbox_events (
    event_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    aggregate_id UUID NOT NULL,
    routing_key VARCHAR(100) NOT NULL,
    payload JSONB NOT NULL,
    published BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_outbox_unpublished ON outbox_events (published, created_at) WHERE published = FALSE;