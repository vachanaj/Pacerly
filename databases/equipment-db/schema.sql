CREATE TABLE IF NOT EXISTS shoes (
    shoe_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL,
    brand VARCHAR(100) NOT NULL,
    model VARCHAR(100) NOT NULL,
    nickname VARCHAR(100),
    max_lifespan_km NUMERIC(8, 2) NOT NULL CHECK (max_lifespan_km > 0),
    current_mileage_km NUMERIC(8, 2) NOT NULL DEFAULT 0 CHECK (current_mileage_km >= 0),
    wear_percentage NUMERIC(5, 2) GENERATED ALWAYS AS (
        CASE
            WHEN max_lifespan_km > 0 THEN ROUND((current_mileage_km / max_lifespan_km) * 100, 2)
            ELSE 0
        END
    ) STORED,
    status VARCHAR(30) NOT NULL DEFAULT 'active',
    is_default BOOLEAN NOT NULL DEFAULT FALSE,
    purchased_at DATE,
    retired_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS shoe_mileage_logs (
    log_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    shoe_id UUID NOT NULL REFERENCES shoes(shoe_id) ON DELETE CASCADE,
    activity_id UUID NOT NULL UNIQUE,
    distance_added_km NUMERIC(8, 2) NOT NULL CHECK (distance_added_km > 0),
    logged_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);