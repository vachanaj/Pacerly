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
from fastapi.middleware.cors import CORSMiddleware

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
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


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