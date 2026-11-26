#Requires -Version 5.1
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$RootDir = Get-Location

$Directories = @(
    "backend/activity-service/app",
    "backend/activity-service/tests",
    "backend/equipment-service/app",
    "backend/equipment-service/tests",
    "backend/adaptive-pacing-service/app",
    "backend/adaptive-pacing-service/tests",
    "databases/activities-db",
    "databases/equipment-db",
    "databases/paces-db"
)

foreach ($dir in $Directories) {
    $fullPath = Join-Path $RootDir $dir
    New-Item -ItemType Directory -Path $fullPath -Force | Out-Null
}

function Write-Utf8File {
    param (
        [string]$RelativePath,
        [string]$Content
    )
    $targetPath = Join-Path $RootDir $RelativePath
    $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText($targetPath, $Content.TrimStart("`r", "`n"), $utf8NoBom)
}

# .gitignore
$GitIgnore = @'
# Byte-compiled / optimized / DLL files
__pycache__/
*.py[cod]
*$py.class

# Virtual environments & build artifacts
.venv/
venv/
ENV/
build/
dist/
*.egg-info/
.pytest_cache/
.ruff_cache/

# Environment & local secrets
.env
.env.*
!.env.example

# Editor / OS files
.vscode/
.idea/
.DS_Store
Thumbs.db
'@
Write-Utf8File -RelativePath ".gitignore" -Content $GitIgnore

# docker-compose.yml (includes activities-db, equipment-db, rabbitmq, and paces-db)
$DockerCompose = @'
services:
  activities-db:
    image: postgres:16-alpine
    container_name: pacerly-activities-db
    environment:
      POSTGRES_DB: activities
      POSTGRES_USER: pacerly
      POSTGRES_PASSWORD: pacerly_dev
    ports:
      - "5433:5432"
    volumes:
      - activities_data:/var/lib/postgresql/data
      - ./databases/activities-db/schema.sql:/docker-entrypoint-initdb.d/init.sql:ro
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U pacerly -d activities"]
      interval: 5s
      timeout: 5s
      retries: 5

  equipment-db:
    image: postgres:16-alpine
    container_name: pacerly-equipment-db
    environment:
      POSTGRES_DB: equipment
      POSTGRES_USER: pacerly
      POSTGRES_PASSWORD: pacerly_dev
    ports:
      - "5434:5432"
    volumes:
      - equipment_data:/var/lib/postgresql/data
      - ./databases/equipment-db/schema.sql:/docker-entrypoint-initdb.d/init.sql:ro
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U pacerly -d equipment"]
      interval: 5s
      timeout: 5s
      retries: 5

  paces-db:
    image: postgres:16-alpine
    container_name: pacerly-paces-db
    environment:
      POSTGRES_DB: paces
      POSTGRES_USER: pacerly
      POSTGRES_PASSWORD: pacerly_dev
    ports:
      - "5435:5432"
    volumes:
      - paces_data:/var/lib/postgresql/data
      - ./databases/paces-db/schema.sql:/docker-entrypoint-initdb.d/init.sql:ro
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U pacerly -d paces"]
      interval: 5s
      timeout: 5s
      retries: 5

  rabbitmq:
    image: rabbitmq:3.13-management-alpine
    container_name: pacerly-rabbitmq
    environment:
      RABBITMQ_DEFAULT_USER: pacerly
      RABBITMQ_DEFAULT_PASS: pacerly_dev
    ports:
      - "5672:5672"
      - "15672:15672"
    healthcheck:
      test: ["CMD", "rabbitmq-diagnostics", "-q", "ping"]
      interval: 5s
      timeout: 5s
      retries: 5

volumes:
  activities_data:
  equipment_data:
  paces_data:
'@
Write-Utf8File -RelativePath "docker-compose.yml" -Content $DockerCompose

# databases/paces-db/schema.sql
$PacesSchema = @'
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
'@
Write-Utf8File -RelativePath "databases/paces-db/schema.sql" -Content $PacesSchema

# Service boilerplate files matching backend.zip layout
$Dockerfile = @'
FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
'@

$Pyproject = @'
[project]
name = "pacerly-service"
version = "0.1.0"
requires-python = ">=3.11"
'@

$Requirements = @'
fastapi>=0.110.0
uvicorn[standard]>=0.27.0
asyncpg>=0.29.0
aio-pika>=9.4.0
pydantic>=2.6.0
pytest>=8.0.0
httpx>=0.27.0
'@

$PacingMain = @'
import asyncio
import json
import os
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from typing import Annotated
from uuid import UUID

import aio_pika
import asyncpg
from fastapi import FastAPI, Header
from pydantic import BaseModel

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://pacerly:pacerly_dev@localhost:5435/paces",
)
RABBITMQ_URL = os.getenv(
    "RABBITMQ_URL",
    "amqp://pacerly:pacerly_dev@localhost:5672/",
)
DEFAULT_BASELINE_PACE_SEC = int(os.getenv("DEFAULT_BASELINE_PACE_SEC", "330"))

EXCHANGE_NAME = "pacerly.events"
QUEUE_NAME = "adaptive-pacing.activity.logged"
ROUTING_KEY = "activity.logged"

DEFAULT_TEST_USER = UUID("11111111-1111-1111-1111-111111111111")

db_pool: asyncpg.Pool | None = None


class PaceProfileResponse(BaseModel):
    user_id: UUID
    rolling_7d_distance_km: float
    rolling_7d_fatigue_score: float
    fatigue_state: str
    pace_adjustment_factor: float
    target_easy_pace_sec: int
    target_tempo_pace_sec: int
    target_interval_pace_sec: int
    target_long_run_pace_sec: int
    last_recalculated_at: datetime


def compute_workout_load(
    duration_sec: int,
    avg_pace_sec_per_km: int,
    workout_type: str,
    baseline_pace_sec: int,
) -> float:
    duration_min = duration_sec / 60.0
    intensity_ratio = baseline_pace_sec / max(avg_pace_sec_per_km, 1)
    type_weight = {
        "easy": 0.85,
        "recovery": 0.70,
        "long": 1.15,
        "tempo": 1.25,
        "interval": 1.35,
    }.get((workout_type or "").lower(), 1.0)
    clamped_intensity = max(0.75, min(1.40, intensity_ratio))
    return round(duration_min * clamped_intensity * type_weight * 0.1, 2)


def derive_pace_targets(
    rolling_7d_fatigue_score: float,
    baseline_pace_sec: int,
) -> tuple[str, float, dict[str, int]]:
    if rolling_7d_fatigue_score >= 120:
        fatigue_state = "overreaching"
        adjustment = 1.06
    elif rolling_7d_fatigue_score >= 75:
        fatigue_state = "fatigued"
        adjustment = 1.03
    elif rolling_7d_fatigue_score >= 25:
        fatigue_state = "optimal"
        adjustment = 1.00
    else:
        fatigue_state = "fresh"
        adjustment = 0.99

    targets = {
        "target_easy_pace_sec": round(baseline_pace_sec * 1.15 * adjustment),
        "target_long_run_pace_sec": round(baseline_pace_sec * 1.10 * adjustment),
        "target_tempo_pace_sec": round(baseline_pace_sec * 0.96 * adjustment),
        "target_interval_pace_sec": round(baseline_pace_sec * 0.88 * adjustment),
    }
    return fatigue_state, adjustment, targets


async def recalculate_user_profile(conn: asyncpg.Connection, user_id: UUID) -> dict:
    cutoff = datetime.now(UTC) - timedelta(days=7)
    agg = await conn.fetchrow(
        """
        SELECT
            COALESCE(SUM(distance_km), 0) AS rolling_7d_distance_km,
            COALESCE(SUM(training_load_score), 0) AS rolling_7d_fatigue_score
        FROM fatigue_activity_ledger
        WHERE user_id = $1 AND activity_date >= $2
        """,
        user_id,
        cutoff,
    )

    dist_7d = float(agg["rolling_7d_distance_km"])
    fatigue_7d = float(agg["rolling_7d_fatigue_score"])
    now = datetime.now(UTC)

    fatigue_state, adjustment, targets = derive_pace_targets(
        fatigue_7d, DEFAULT_BASELINE_PACE_SEC
    )

    row = await conn.fetchrow(
        """
        INSERT INTO adaptive_pace_profiles (
            user_id,
            rolling_7d_distance_km,
            rolling_7d_fatigue_score,
            fatigue_state,
            pace_adjustment_factor,
            target_easy_pace_sec,
            target_tempo_pace_sec,
            target_interval_pace_sec,
            target_long_run_pace_sec,
            last_recalculated_at
        )
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
        ON CONFLICT (user_id) DO UPDATE SET
            rolling_7d_distance_km = EXCLUDED.rolling_7d_distance_km,
            rolling_7d_fatigue_score = EXCLUDED.rolling_7d_fatigue_score,
            fatigue_state = EXCLUDED.fatigue_state,
            pace_adjustment_factor = EXCLUDED.pace_adjustment_factor,
            target_easy_pace_sec = EXCLUDED.target_easy_pace_sec,
            target_tempo_pace_sec = EXCLUDED.target_tempo_pace_sec,
            target_interval_pace_sec = EXCLUDED.target_interval_pace_sec,
            target_long_run_pace_sec = EXCLUDED.target_long_run_pace_sec,
            last_recalculated_at = EXCLUDED.last_recalculated_at
        RETURNING *
        """,
        user_id,
        dist_7d,
        fatigue_7d,
        fatigue_state,
        adjustment,
        targets["target_easy_pace_sec"],
        targets["target_tempo_pace_sec"],
        targets["target_interval_pace_sec"],
        targets["target_long_run_pace_sec"],
        now,
    )
    return dict(row)


async def handle_activity_logged(message: aio_pika.IncomingMessage) -> None:
    async with message.process():
        event = json.loads(message.body.decode())
        activity_id = UUID(event["activity_id"])
        user_id = UUID(event["user_id"])
        distance_km = float(event["total_distance_km"])
        duration_sec = int(event["total_duration_sec"])
        avg_pace = int(event["avg_pace_sec_per_km"])
        workout_type = event.get("workout_type", "easy")
        started_at_raw = event.get("started_at")
        activity_date = (
            datetime.fromisoformat(started_at_raw)
            if started_at_raw
            else datetime.now(UTC)
        )
        if activity_date.tzinfo is None:
            activity_date = activity_date.replace(tzinfo=UTC)

        load_score = compute_workout_load(
            duration_sec=duration_sec,
            avg_pace_sec_per_km=avg_pace,
            workout_type=workout_type,
            baseline_pace_sec=DEFAULT_BASELINE_PACE_SEC,
        )

        async with db_pool.acquire() as conn, conn.transaction():
            inserted_id = await conn.fetchval(
                """
                INSERT INTO fatigue_activity_ledger (
                    activity_id, user_id, distance_km, duration_sec,
                    avg_pace_sec_per_km, training_load_score, activity_date
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7)
                ON CONFLICT (activity_id) DO NOTHING
                RETURNING activity_id
                """,
                activity_id,
                user_id,
                distance_km,
                duration_sec,
                avg_pace,
                load_score,
                activity_date,
            )
            if inserted_id:
                await recalculate_user_profile(conn, user_id)


async def consume_events() -> None:
    connection = await aio_pika.connect_robust(RABBITMQ_URL)
    channel = await connection.channel()
    await channel.set_qos(prefetch_count=10)

    exchange = await channel.declare_exchange(
        EXCHANGE_NAME, aio_pika.ExchangeType.TOPIC, durable=True
    )
    queue = await channel.declare_queue(QUEUE_NAME, durable=True)
    await queue.bind(exchange, routing_key=ROUTING_KEY)
    await queue.consume(handle_activity_logged)

    try:
        await asyncio.Future()
    except asyncio.CancelledError:
        pass
    finally:
        await connection.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    global db_pool
    db_pool = await asyncpg.create_pool(DATABASE_URL, min_size=2, max_size=10)
    consumer_task = asyncio.create_task(consume_events())
    yield
    consumer_task.cancel()
    await consumer_task
    await db_pool.close()


app = FastAPI(title="Pacerly Adaptive Pacing Service", lifespan=lifespan)


def format_profile(row: dict) -> PaceProfileResponse:
    return PaceProfileResponse(
        user_id=row["user_id"],
        rolling_7d_distance_km=float(row["rolling_7d_distance_km"]),
        rolling_7d_fatigue_score=float(row["rolling_7d_fatigue_score"]),
        fatigue_state=row["fatigue_state"],
        pace_adjustment_factor=float(row["pace_adjustment_factor"]),
        target_easy_pace_sec=row["target_easy_pace_sec"],
        target_tempo_pace_sec=row["target_tempo_pace_sec"],
        target_interval_pace_sec=row["target_interval_pace_sec"],
        target_long_run_pace_sec=row["target_long_run_pace_sec"],
        last_recalculated_at=row["last_recalculated_at"],
    )


@app.get("/health")
async def health_check():
    return {"status": "ok", "service": "adaptive-pacing-service"}


@app.get("/paces", response_model=PaceProfileResponse)
async def get_paces(
    x_user_id: Annotated[UUID, Header()] = DEFAULT_TEST_USER,
):
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM adaptive_pace_profiles WHERE user_id = $1",
            x_user_id,
        )
        data = dict(row) if row else await recalculate_user_profile(conn, x_user_id)
    return format_profile(data)


@app.post("/paces/recalculate", response_model=PaceProfileResponse)
async def trigger_recalculate(
    x_user_id: Annotated[UUID, Header()] = DEFAULT_TEST_USER,
):
    async with db_pool.acquire() as conn, conn.transaction():
        data = await recalculate_user_profile(conn, x_user_id)
    return format_profile(data)
'@

$PlaceholderMain = @'
from fastapi import FastAPI

app = FastAPI()


@app.get("/health")
async def health_check():
    return {"status": "ok"}
'@

$PlaceholderSql = @"
-- Schema placeholder
"@

$SampleTest = @'
from fastapi.testclient import TestClient
from app.main import app


def test_health():
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
'@

foreach ($svc in @("activity-service", "equipment-service", "adaptive-pacing-service")) {
    Write-Utf8File -RelativePath "backend/$svc/Dockerfile" -Content $Dockerfile
    Write-Utf8File -RelativePath "backend/$svc/pyproject.toml" -Content $Pyproject
    Write-Utf8File -RelativePath "backend/$svc/requirements.txt" -Content $Requirements
    Write-Utf8File -RelativePath "backend/$svc/app/__init__.py" -Content ""
    Write-Utf8File -RelativePath "backend/$svc/tests/test_main.py" -Content $SampleTest

    if ($svc -eq "adaptive-pacing-service") {
        Write-Utf8File -RelativePath "backend/$svc/app/main.py" -Content $PacingMain
    } else {
        Write-Utf8File -RelativePath "backend/$svc/app/main.py" -Content $PlaceholderMain
    }
}

Write-Utf8File -RelativePath "databases/activities-db/schema.sql" -Content $PlaceholderSql
Write-Utf8File -RelativePath "databases/equipment-db/schema.sql" -Content $PlaceholderSql

Write-Host "Repository structure created successfully at $RootDir" -ForegroundColor Green